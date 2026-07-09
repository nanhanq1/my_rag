import ast
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============ 大模型 / 向量模型 ============
    openai_api_key: str
    openai_base_url: str
    openai_model_name: str
    embedding_model: str

    # ============ 文档解析 / 检索参数 ============
    supported_extensions: Annotated[list[str], NoDecode]
    chunk_size: int
    chunk_overlap: int
    top_k: int
    score_threshold: float

    # ============ 文档存储 / 数据库 / 向量库路径 ============
    max_file_size_mb: int
    documents_save_path: str
    database_file_path: str
    chroma_path: str

    @field_validator("supported_extensions", mode="before")
    @classmethod
    def parse_supported_extensions(cls, value):
        if isinstance(value, str):
            return ast.literal_eval(value)
        return value

# 创建全局配置对象
settings = AppSettings()

if __name__ == "__main__":
    print(settings.supported_extensions)
    print(settings.chroma_path)
