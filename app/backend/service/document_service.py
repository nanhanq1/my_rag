# -*- coding: utf-8 -*-
"""
DocumentService：负责文件管理。

职责：
  - 校验文件类型与大小
  - 将上传文件保存到指定目录（config.documents_save_path）
  - 将文件元信息写入 SQLite 数据库（documents 表）
  - 调用 VectorService 完成向量化入库
  - 列出 / 按文件名搜索 / 删除文档（同时清理磁盘文件与向量）
  - 上传去重：同名文件视为重复，直接返回已有记录
"""
import mimetypes
import os
import uuid

from fastapi import UploadFile

from app.backend.config import settings
from app.backend.db.models import Document
from app.backend.db.session import SessionLocal

# 部分系统（如 Windows）对 .md / .csv 没有内置 MIME 映射，这里补充常用类型
_EXT_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
}


class DocumentService:
    def __init__(self, vector_service):
        self.vector_service = vector_service
        os.makedirs(settings.documents_save_path, exist_ok=True)

    # ---------- 上传 ----------
    def upload(self, file: UploadFile):
        """保存单个文件并入库。同名文件视为重复，直接返回已有记录。

        参数:
            filename:     原始文件名
            content:      文件二进制内容
            content_type: 浏览器提供的 MIME 类型（可选）
        返回: 文档信息字典；命中已有记录时额外带 deduplicated=True
        """
        ext = os.path.splitext(file.filename)[-1].lower()
        if ext not in settings.supported_extensions:
            raise ValueError(
                f"不支持的文件类型: {ext}（支持 {', '.join(settings.supported_extensions)}）"
            )

        size = len(file.file.read())
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        if size > max_bytes:
            raise ValueError(f"文件大小超过限制（最大 {settings.max_file_size_mb} MB）")

        # MIME 类型：优先用浏览器提供的，否则按扩展名推断（含自定义补充映射）
        mime_type = (
            file.content_type
            or mimetypes.guess_type(file.filename)[0]
            or _EXT_MIME.get(ext)
            or "application/octet-stream"
        )

        # SQLAlchemy的Session支持上下文管理器。with 退出时会：
        # 1.若发生未捕获异常 → 自动rollback()
        # 2.始终close()
        # 不需要写繁琐的try/except
        with SessionLocal() as session:
            # 同名文件已存在 → 视为重复上传，直接返回已有记录，不再落盘/入库/向量化
            existing = (
                session.query(Document)
                .filter(Document.original_filename == file.filename)
                .first()
            )
            if existing is not None:
                return {**existing.to_dict(), "deduplicated": True}

            # 以唯一名称落盘，避免重名覆盖；保留原始名记录在数据库
            stored_name = f"{uuid.uuid4().hex}{ext}"
            storage_path = os.path.join(settings.documents_save_path, stored_name)
            with open(storage_path, "wb") as f:
                f.write(file.file.read())

            doc = Document(
                original_filename=file.filename,
                file_size=size,
                mime_type=mime_type,
                storage_path=storage_path,
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)

            # 向量化入库
            try:
                self.vector_service.add_file(storage_path, doc.id, file.filename)
            except Exception:
                # 向量化失败则回滚数据库记录与磁盘文件，保持一致性
                session.delete(doc)
                session.commit()
                if os.path.exists(storage_path):
                    os.remove(storage_path)
                raise

            return {**doc.to_dict(), "deduplicated": False}

    # ---------- 列表 / 搜索 ----------
    def list(self, keyword=None, page=1, page_size=10):
        """列出文档，支持按原始文件名模糊搜索 + 分页。

        返回 dict：{"documents": [...], "total": N, "page": P,
                  "page_size": S, "total_pages": M}
        """
        with SessionLocal() as session:
            query = session.query(Document)
            if keyword:
                query = query.filter(Document.original_filename.like(f"%{keyword}%"))

            total = query.count()

            docs = (
                query.order_by(Document.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            total_pages = (total + page_size - 1) // page_size if total else 0
            return {
                "documents": [d.to_dict() for d in docs],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }

    # ---------- 删除 ----------
    def delete(self, doc_id):
        """删除文档：数据库记录 + 磁盘文件 + 向量。返回是否删除成功。"""
        with SessionLocal() as session:
            doc = session.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return False

            # 删除磁盘文件
            if doc.storage_path and os.path.exists(doc.storage_path):
                try:
                    os.remove(doc.storage_path)
                except OSError:
                    pass
            # 删除数据库记录
            session.delete(doc)
            session.commit()
            return True
