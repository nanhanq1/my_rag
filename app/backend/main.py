import json
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
from pydantic import BaseModel
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from app.backend.db.session import init_db
from app.backend.db.models import User
from app.backend.logger import logger
from app.backend.service import auth_service, conversation_service
from app.backend.service.chat_service import ChatService
from app.backend.service.document_service import DocumentService
from app.backend.service.vector_service import VectorService

app = FastAPI(title="企业知识库", version="1.0.0")

# Path(__file__).resolve() 获得当前文件路径
BASE_DIR = Path(__file__).resolve().parent.parent
# 前端目录
WEB_DIR = BASE_DIR / "web"

# 初始化数据库
init_db()

vector_service = VectorService()
chat_service = ChatService(vector_service)
document_service = DocumentService(vector_service)


# ==================== 认证中间件 ====================
def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """从 Authorization: Bearer <token> 提取 token，返回用户对象。未登录抛 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization[7:]
    user = auth_service.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


# ==================== 认证接口 ====================
class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def auth_register(req: AuthRequest):
    """用户注册。用户名已存在时返回 400。"""
    result = auth_service.register(req.username, req.password)
    if result is None:
        raise HTTPException(status_code=400, detail="用户名已存在")
    token, user = result
    return {"token": token, "user": user.to_dict()}


@app.post("/auth/login")
def auth_login(req: AuthRequest):
    """用户登录。用户名或密码错误时返回 400。"""
    result = auth_service.login(req.username, req.password)
    if result is None:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token, user = result
    return {"token": token, "user": user.to_dict()}


@app.post("/auth/logout")
def auth_logout(user: User = Depends(get_current_user), authorization: str = Header(None)):
    """注销：从内存中移除 token。"""
    if authorization and authorization.startswith("Bearer "):
        auth_service.logout(authorization[7:])
    return {"ok": True}


@app.get("/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return {"user": user.to_dict()}


# ==================== 对话管理接口 ====================
@app.get("/conversations")
def list_conversations_endpoint(user: User = Depends(get_current_user)):
    """列出当前用户的所有对话，按更新时间倒序。"""
    convs = conversation_service.list_conversations(user.id)
    return {"conversations": [c.to_dict() for c in convs]}


@app.post("/conversations")
def create_conversation_endpoint(user: User = Depends(get_current_user)):
    """创建新对话。"""
    conv = conversation_service.create_conversation(user.id)
    return conv.to_dict()


@app.delete("/conversations/{conv_id}")
def delete_conversation_endpoint(conv_id: int, user: User = Depends(get_current_user)):
    """删除对话及其所有消息。仅限对话所有者。"""
    ok = conversation_service.delete_conversation(conv_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@app.get("/conversations/{conv_id}/messages")
def get_messages_endpoint(conv_id: int, user: User = Depends(get_current_user)):
    """加载某个对话的所有消息（按时间正序）。"""
    conv = conversation_service.get_conversation(conv_id, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = conversation_service.list_messages(conv_id)
    return {"messages": [m.to_dict() for m in msgs]}


# ==================== 文档管理接口（加认证保护） ====================
@app.get("/documents")
def list_documents(keyword: Optional[str] = None, page: int = 1, page_size: int = 10,
                   user: User = Depends(get_current_user)):
    return document_service.list(keyword, page, page_size)


@app.post("/documents/upload")
def upload_document(files: List[UploadFile] = File(...),
                    user: User = Depends(get_current_user)):
    results = []
    for file in files:
        try:
            info = document_service.upload(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        results.append(info)
    return {"results": results}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(get_current_user)):
    ok = document_service.delete(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": doc_id}


# ==================== 对话聊天接口 ====================
class ChatRequest(BaseModel):
    message: str
    conversation_id: int


@app.post("/chat")
def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    """流式对话：将用户消息存入数据库，通过 SSE 流式返回检索结果和模型回复，
    最后将完整回复存入数据库。"""
    logger.info(f"聊天请求: {req.message}, conversation_id={req.conversation_id}")

    conv = conversation_service.get_conversation(req.conversation_id, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 存储用户消息
    conversation_service.add_message(conv.id, "user", req.message)

    # 新对话的首条消息自动设为标题
    if conv.title == "新对话":
        title = req.message[:20] + ("..." if len(req.message) > 20 else "")
        conversation_service.update_title(conv.id, title)

    thread_id = conv.thread_id

    async def stream_response():
        full_content = ""
        all_sources = []
        try:
            async for event in chat_service.astream_chat(req.message, thread_id=thread_id):
                if "sources" in event:
                    all_sources = event["sources"]
                if "content" in event:
                    full_content += event["content"]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            # 流结束后存储助手回复
            if full_content:
                conversation_service.add_message(
                    conv.id, "assistant", full_content,
                    all_sources if all_sources else None
                )
        except Exception:
            error_id = uuid.uuid4().hex
            logger.exception("SSE 对话失败 error_id=%s", error_id)
            yield f"data: {json.dumps({'error': '服务器内部错误，请联系管理员并提供错误编号', 'error_id': error_id}, ensure_ascii=False)}\n\n"
            # 即使出错也保存已生成的部分内容
            if full_content:
                conversation_service.add_message(
                    conv.id, "assistant", full_content,
                    all_sources if all_sources else None
                )

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(stream_response(), media_type="text/event-stream", headers=headers)


# ==================== 页面 & 静态资源 ====================
@app.get("/")
def index():
    logger.info("访问首页")
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.backend.main:app", host="127.0.0.1", port=8080, reload=True)
