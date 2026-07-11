import json
import os
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile
from langgraph_sdk.auth.exceptions import HTTPException
from openai import OpenAI, vector_stores
from pydantic import BaseModel
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from app.backend.db.session import init_db
from app.backend.logger import logger
from app.backend.service.chat_service import ChatService
from app.backend.service.document_service import DocumentService
from app.backend.service.vector_service import VectorService

app = FastAPI(title="RAG企业知识库", version="1.0.0")

# Path(__file__).resolve()获得当前文件路径
BASE_DIR = Path(__file__).resolve().parent.parent
# 前端目录
WEB_DIR = BASE_DIR / "web"

# 初始化数据库
init_db()

vector_service = VectorService()
chat_service = ChatService(vector_service)
document_service = DocumentService(vector_service)


# ==================== 文档上传接口 ===============
@app.get("/documents")
def list_documents(keyword: Optional[str] = None, page: int = 1, page_size: int = 10):
    return document_service.list(keyword, page, page_size)

@app.post("/documents/upload")
def upload_document(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        try:
            info = document_service.upload(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        results.append(info)

    return {"results":  results}

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int):
    ok = document_service.delete(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")

    return {"deleted": doc_id}







# ==================== 对话接口 ===================

class ChatRequest(BaseModel):
    message: str
    thread_id: str


@app.post("/chat")
def chat(req: ChatRequest):
    logger.info(f"聊天请求: {req.message}")
    logger.info(f"线程ID: {req.thread_id}")

    thread_id = req.thread_id or f"sess-{uuid.uuid4().hex[:12]}"

    async def stream_response():
        try:
            # astream_chat 产出结构化事件（{"sources": ...} / {"content": ...}），直接序列化
            async for event in chat_service.astream_chat(req.message, thread_id=thread_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            # 不向客户端回吐原始异常（可能含路径/SQL/栈帧），只返回通用消息 + error_id 便于排查
            error_id = uuid.uuid4().hex
            logger.exception("SSE 对话失败 error_id=%s", error_id)
            yield f"data: {json.dumps({'error': '服务器内部错误，请联系管理员并提供错误编号', 'error_id': error_id}, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(stream_response(), media_type="text/event-stream", headers=headers)

# /chat?question=xxx
@app.get("/chat2")
def chat2(question: str):
    logger.info(f"聊天请求: {question}")
    client = OpenAI(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
        api_key="sk-ws-H.EMIMMMD.Ubom.MEUCIDYmaGtoLwamCG1d6JQFqSN5EAzVundhZfApRqwLkhwoAiEA80Dl8lc41yy0vvPpw4B-akbKfq-psHV793IQIgyGMNI",
        base_url="https://ws-10v53f71kp1ik6yu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    completion = client.chat.completions.create(
        model="qwen3.7-plus",
        # 此处以qwen-plus为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=[{'role': 'system', 'content': '我是思途AI助手'},
                  {'role': 'user', 'content': question}],
        stream=True,
        stream_options={"include_usage": True}
    )

    def stream_response():
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    return StreamingResponse(stream_response(), media_type="text/plain;charset=utf-8")


@app.get("/chat1")
def chat1(question: str):
    logger.info(f"用户问题：{question}")
    client = OpenAI(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
        api_key="sk-ws-H.EMIMMMD.Ubom.MEUCIDYmaGtoLwamCG1d6JQFqSN5EAzVundhZfApRqwLkhwoAiEA80Dl8lc41yy0vvPpw4B-akbKfq-psHV793IQIgyGMNI",
        base_url="https://ws-10v53f71kp1ik6yu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )

    completion = client.chat.completions.create(
        # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        model="qwen3.7-plus",
        messages=[
            {"role": "system", "content": "我是思途AI助手"},
            {"role": "user", "content": question},
        ]
    )
    print(completion.model_dump_json())
    logger.info(f"模型输出：{completion.choices[0].message.content}")
    return completion.choices[0].message.content

@app.get("/chat_stream")
def chat_stream(question: str):
    logger.info(f"聊天请求: {question}")
    client = OpenAI(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
        api_key="sk-ws-H.EMIMMMD.Ubom.MEUCIDYmaGtoLwamCG1d6JQFqSN5EAzVundhZfApRqwLkhwoAiEA80Dl8lc41yy0vvPpw4B-akbKfq-psHV793IQIgyGMNI",
        base_url="https://ws-10v53f71kp1ik6yu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    completion = client.chat.completions.create(
        model="qwen3.7-plus",
        # 此处以qwen-plus为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=[{'role': 'system', 'content': '我是思途AI助手'},
                  {'role': 'user', 'content': question}],
        stream=True,
        stream_options={"include_usage": True}
    )
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

@app.get("/")
def index():
    logger.info("访问首页")
    return FileResponse(WEB_DIR / "index.html")

@app.get("/students")
def get_students():
    logger.info("获取学生列表")
    return [
        {"id": 1, "name": "张三"},
        {"id": 2, "name": "李四"},
        {"id": 3, "name": "王五"},
    ]

# 托管前端静态资源，访问路径：/static/css/style.css
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)


