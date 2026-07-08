import os
from pathlib import Path

from fastapi import FastAPI
from openai import OpenAI
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from app.backend.logger import logger

app = FastAPI(title="RAG企业知识库", version="1.0.0")

# Path(__file__).resolve()获得当前文件路径
BASE_DIR = Path(__file__).resolve().parent.parent
# 前端目录
WEB_DIR = BASE_DIR / "web"

@app.get("/chat")
def chat(question: str):
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


