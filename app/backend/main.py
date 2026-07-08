from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

app = FastAPI(title="RAG企业知识库", version="1.0.0")

# Path(__file__).resolve()获得当前文件路径
BASE_DIR = Path(__file__).resolve().parent.parent
# 前端目录
WEB_DIR = BASE_DIR / "web"

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


# 托管前端静态资源，访问路径：/static/css/style.css
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)


