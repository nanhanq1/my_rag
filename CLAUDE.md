# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目简介

RAG 企业知识库 - 一款企业知识库问答应用。FastAPI 后端服务于 Vue 3 前端；目标架构是从上传的企业文档构成的向量库中检索答案（LangChain + Chroma + DashScope/Qwen）。项目处于早期开发阶段：RAG 流水线的大部分已在 `requirements.txt` 中声明，但代码中**尚未实现**。

- Python 3.12.8，虚拟环境位于 `.venv/`（Windows）。激活方式：`source .venv/Scripts/activate`。
- 所有界面文案、日志、git 提交信息均为中文 - 编辑时请保持一致。

## 常用命令

首次安装依赖：
```bash
.venv/Scripts/pip install -r requirements.txt
```

**在项目根目录下**启动开发服务器（`app.backend...` 这类导入路径要求仓库根目录位于 `sys.path` 上）：
```bash
.venv/Scripts/uvicorn app.backend.main:app --reload --port 8080
```
然后访问 http://127.0.0.1:8080/（界面）或 http://127.0.0.1:8080/docs（OpenAPI 文档）。

> 注意：`app/backend/main.py` 中还有一个 `if __name__ == "__main__"` 块，调用 `uvicorn.run("main:app", reload=True)`，但 `"main:app"` 仅在当前工作目录为 `app/backend/` 时才能解析，这与包式导入相冲突。请优先使用上方的 uvicorn CLI 形式。本项目没有测试套件，也未配置 linter/formatter。

## 架构说明

**后端 - `app/backend/`**
- `main.py`：FastAPI 应用，包含全部路由。目前仅有直连大模型的对话（无检索）。存在三个对话变体作为开发脚手架：`/chat`（GET，以 `text/plain` 流式输出原始 token）、`/chat1`（GET，非流式）、`/chat_stream`（GET，打印到 stdout - 不返回内容）。此外还有 `/`（返回 `index.html`）和 `/students`（桩数据）。静态资源以 `/static` 挂载，来源目录为 `app/web/`。
- `logger.py`：loguru 封装，由 `.env` 驱动（`LOG_CONSOLE_*`、`LOG_FILE_*`、`LOG_FILE_RETENTION`）。写入 `logs/app_YYYYMMDD.log`，按天轮转。通过 `.patch(fix_log_position)` 遍历调用栈、跳过 loguru 及 `logger.py` 自身帧，使日志记录显示真正的业务调用方文件/行号。请始终 `from app.backend.logger import logger` 并使用这个已 patch 的单例。

**前端 - `app/web/`**
- Vue 3 通过本地内置的 CDN 构建版加载（`js/vue.global.prod.js`）- **无构建步骤，无 npm**。直接编辑 `index.html` + `js/app.js` + `css/style.css` 即可。默认深色主题；`html.dark` 类名切换 CSS 变量。

**大模型对接**：阿里云百炼（DashScope）通过 OpenAI SDK 访问 OpenAI 兼容端点（`...maas.aliyuncs.com/compatible-mode/v1`），模型 `qwen3.7-plus`，系统提示词 `我是思途AI助手`。

## 关键：前后端接口契约不一致

前端（`app/web/js/app.js`）所期望的后端接口，`main.py` **尚未**实现。在对接 RAG 层时，现有前端调用即定义了目标 API 契约：

- `POST /chat`，请求体 JSON `{message, thread_id}` -> Server-Sent-Events 流，由 `data:` 帧组成。帧载荷为 JSON 对象，含 `content`（token）、`sources`（`{source, score}` 数组）或 `error`；流以 `data: [DONE]` 结束。（后端当前的 `GET /chat?question=` 返回纯文本，不含上述任何帧封装。）
- `GET /documents?page=&page_size=&keyword=` -> `{documents:[{id, original_filename, file_size, created_at, ...}], total, total_pages}`
- `POST /documents/upload`（multipart `files`）-> `{documents:[{..., deduplicated}]}`（前端展示每个文件 上传中->向量化中 的进度）
- `DELETE /documents/{id}`
- 支持的上传格式：`.txt .pdf .csv .md`（前端校验）

## 安全提示

DashScope API Key 被**硬编码在 `app/backend/main.py`** 中并已提交到 git（出现在三个路由处理函数里）。`python-dotenv` 与 `.env`（已 gitignore）已用于日志配置 - 请将 Key 移入 `.env` 并通过 `os.getenv` 读取，而不是在各处理函数中重复硬编码。
