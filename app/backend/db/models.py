"""
数据库模型定义：上传文档对应的ORM映射
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 原始文件名称
    original_filename = Column(String(255), nullable=False)
    # 文件大小（单位：字节）
    file_size = Column(BigInteger, nullable=False)
    # 文件 MIME 类型
    mime_type = Column(String(128), nullable=True)
    # 文件存储路径
    storage_path = Column(String(512), nullable=False)
    # 文档创建时间
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    # 文档更新时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # to_dict 是 Document ORM 模型上的序列化方法，把数据库里的 Document 对象转成普通 Python 字典，
    # 供 API 以 JSON 返回给前端。
    def to_dict(self):
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "storage_path": self.storage_path,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }