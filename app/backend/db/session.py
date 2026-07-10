# -*- coding: utf-8 -*-
"""
数据库连接与会话：SQLite 引擎、Session 工厂及建表初始化。
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.config import settings
from app.backend.db.models import Base

# 确保数据库文件所在目录存在
os.makedirs(os.path.dirname(settings.database_file_path), exist_ok=True)

# SQLite 引擎（check_same_thread=False 以兼容 FastAPI 多线程）
engine = create_engine(
    f"sqlite:///{settings.database_file_path}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """创建数据库表（若不存在）。应用启动时调用一次。"""
    # 所有继承 Base 的模型会注册到 Base.metadata 里
    # 然后 Base.metadata.create_all(engine) 会创建所有表
    Base.metadata.create_all(engine)
