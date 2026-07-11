"""
轻量预览服务器（仅用于查看前端重设计效果）。
不加载 LangChain / Chroma / dashscope，用内存假数据模拟全部接口。
运行：.venv/bin/python preview_server.py
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
from pydantic import BaseModel
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

WEB_DIR = Path(__file__).resolve().parent / "app" / "web"

app = FastAPI(title="企业知识库(预览)", version="preview")

# ==================== 内存假数据 ====================
DB = {
    "users": {},          # username -> {id, username, password}
    "tokens": {},         # token -> username
    "conversations": [],  # {id, title, thread_id, updated_at}
    "messages": {},       # conv_id -> [{role, content, sources}]
    "documents": [],      # {id, original_filename, file_size, created_at}
    "seq": {"user": 0, "conv": 0, "doc": 0},
}


def _seed():
    """预置一个演示账号和一些内容，方便直接查看效果。"""
    DB["seq"]["user"] += 1
    uid = DB["seq"]["user"]
    DB["users"]["demo"] = {"id": uid, "username": "demo", "password": "demo123"}

    demo_docs = [
        ("员工手册-2024版.pdf", 2_480_000),
        ("产品需求文档-知识库.md", 68_400),
        ("财务报销制度.txt", 12_800),
        ("客户常见问题FAQ.csv", 45_200),
        ("技术架构说明.md", 91_600),
    ]
    for name, size in demo_docs:
        DB["seq"]["doc"] += 1
        DB["documents"].append({
            "id": DB["seq"]["doc"],
            "original_filename": name,
            "file_size": size,
            "created_at": "2024-06-0{} 10:2{}".format(DB["seq"]["doc"], DB["seq"]["doc"]),
        })

    # 预置对话
    DB["seq"]["conv"] += 1
    cid = DB["seq"]["conv"]
    DB["conversations"].append({
        "id": cid, "title": "报销制度有哪些规定？", "thread_id": "t1",
        "updated_at": "2024-06-05 10:20",
    })
    DB["messages"][cid] = [
        {"role": "user", "content": "报销制度有哪些规定？", "sources": []},
        {"role": "assistant",
         "content": "根据《财务报销制度》，主要规定如下：\n\n1. 差旅费需在出差结束后 5 个工作日内提交报销申请。\n2. 单张发票金额超过 500 元需附上审批单。\n3. 餐饮招待费需注明招待对象与事由。\n\n如需了解具体标准，可查阅知识库中的完整制度文档。",
         "sources": [
             {"source": "财务报销制度.txt", "score": 0.92},
             {"source": "员工手册-2024版.pdf", "score": 0.81},
         ]},
    ]


_seed()


def _new_token(username: str) -> str:
    token = "tok_" + str(int(time.time() * 1000)) + "_" + username
    DB["tokens"][token] = username
    return token


def _user_dict(username: str):
    u = DB["users"][username]
    return {"id": u["id"], "username": u["username"]}


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization[7:]
    username = DB["tokens"].get(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return _user_dict(username)


# ==================== 认证 ====================
class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def auth_register(req: AuthRequest):
    if req.username in DB["users"]:
        raise HTTPException(status_code=400, detail="用户名已存在")
    DB["seq"]["user"] += 1
    DB["users"][req.username] = {"id": DB["seq"]["user"], "username": req.username, "password": req.password}
    token = _new_token(req.username)
    return {"token": token, "user": _user_dict(req.username)}


@app.post("/auth/login")
def auth_login(req: AuthRequest):
    u = DB["users"].get(req.username)
    if not u or u["password"] != req.password:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = _new_token(req.username)
    return {"token": token, "user": _user_dict(req.username)}


@app.post("/auth/logout")
def auth_logout(user=Depends(get_current_user), authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        DB["tokens"].pop(authorization[7:], None)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(user=Depends(get_current_user)):
    return {"user": user}


# ==================== 对话 ====================
@app.get("/conversations")
def list_conversations(user=Depends(get_current_user)):
    return {"conversations": list(reversed(DB["conversations"]))}


@app.post("/conversations")
def create_conversation(user=Depends(get_current_user)):
    DB["seq"]["conv"] += 1
    cid = DB["seq"]["conv"]
    conv = {"id": cid, "title": "新对话", "thread_id": "t" + str(cid),
            "updated_at": time.strftime("%Y-%m-%d %H:%M")}
    DB["conversations"].append(conv)
    DB["messages"][cid] = []
    return conv


@app.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, user=Depends(get_current_user)):
    before = len(DB["conversations"])
    DB["conversations"][:] = [c for c in DB["conversations"] if c["id"] != conv_id]
    if len(DB["conversations"]) == before:
        raise HTTPException(status_code=404, detail="对话不存在")
    DB["messages"].pop(conv_id, None)
    return {"ok": True}


@app.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: int, user=Depends(get_current_user)):
    if conv_id not in DB["messages"]:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"messages": DB["messages"][conv_id]}


# ==================== 文档 ====================
@app.get("/documents")
def list_documents(keyword: Optional[str] = None, page: int = 1, page_size: int = 10,
                   user=Depends(get_current_user)):
    docs = DB["documents"]
    if keyword:
        docs = [d for d in docs if keyword.lower() in d["original_filename"].lower()]
    total = len(docs)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    page_docs = docs[start:start + page_size]
    return {"documents": page_docs, "total": total, "total_pages": total_pages,
            "page": page, "page_size": page_size}


@app.post("/documents/upload")
async def upload_document(files: List[UploadFile] = File(...), user=Depends(get_current_user)):
    results = []
    for file in files:
        content = await file.read()
        DB["seq"]["doc"] += 1
        doc = {"id": DB["seq"]["doc"], "original_filename": file.filename,
               "file_size": len(content), "created_at": time.strftime("%Y-%m-%d %H:%M")}
        DB["documents"].append(doc)
        results.append({**doc, "deduplicated": False})
    return {"results": results}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user=Depends(get_current_user)):
    before = len(DB["documents"])
    DB["documents"][:] = [d for d in DB["documents"] if d["id"] != doc_id]
    if len(DB["documents"]) == before:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": doc_id}


# ==================== 聊天（模拟流式） ====================
class ChatRequest(BaseModel):
    message: str
    conversation_id: int


@app.post("/chat")
def chat(req: ChatRequest, user=Depends(get_current_user)):
    conv = next((c for c in DB["conversations"] if c["id"] == req.conversation_id), None)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")

    DB["messages"].setdefault(conv["id"], []).append(
        {"role": "user", "content": req.message, "sources": []})
    if conv["title"] == "新对话":
        conv["title"] = req.message[:20] + ("..." if len(req.message) > 20 else "")

    reply = (
        "这是预览模式下的模拟回复。你的问题是：「%s」。\n\n"
        "在真实环境中，系统会先从向量知识库检索相关文档片段，再由通义千问模型"
        "结合检索内容生成答案。当前仅用于展示重新设计后的界面效果。"
    ) % req.message
    sources = [
        {"source": "员工手册-2024版.pdf", "score": 0.88},
        {"source": "技术架构说明.md", "score": 0.76},
    ]

    async def stream_response():
        yield "data: %s\n\n" % json.dumps({"sources": sources}, ensure_ascii=False)
        await asyncio.sleep(0.2)
        for ch in reply:
            yield "data: %s\n\n" % json.dumps({"content": ch}, ensure_ascii=False)
            await asyncio.sleep(0.012)
        yield "data: [DONE]\n\n"
        DB["messages"][conv["id"]].append(
            {"role": "assistant", "content": reply, "sources": sources})

    return StreamingResponse(stream_response(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== 页面 & 静态资源 ====================
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
