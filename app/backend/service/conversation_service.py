# -*- coding: utf-8 -*-
"""
对话服务：对话的增删查 + 消息存储与加载。

每条对话有独立的 thread_id（供 LangGraph checkpointer 使用），
消息持久化到 SQLite，刷新/重启后仍可加载历史对话。
"""
import json
import uuid
from datetime import datetime

from app.backend.db.models import Conversation, ChatMessage
from app.backend.db.session import SessionLocal
from app.backend.logger import logger


def create_conversation(user_id: int, title: str = "新对话"):
    """创建新对话，返回对话对象。"""
    thread_id = f"conv-{uuid.uuid4().hex[:16]}"
    with SessionLocal() as session:
        conv = Conversation(user_id=user_id, title=title, thread_id=thread_id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        logger.info(f"创建对话: id={conv.id}, thread_id={thread_id}")
        return conv


def list_conversations(user_id: int):
    """列出用户的所有对话，按更新时间倒序。"""
    with SessionLocal() as session:
        convs = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
        return convs


def get_conversation(conv_id: int, user_id: int):
    """获取单个对话（含权限校验，仅限对话所有者）。"""
    with SessionLocal() as session:
        return (
            session.query(Conversation)
            .filter(Conversation.id == conv_id, Conversation.user_id == user_id)
            .first()
        )


def delete_conversation(conv_id: int, user_id: int) -> bool:
    """删除对话及其所有消息。仅限对话所有者。"""
    with SessionLocal() as session:
        conv = (
            session.query(Conversation)
            .filter(Conversation.id == conv_id, Conversation.user_id == user_id)
            .first()
        )
        if conv is None:
            return False
        session.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id).delete()
        session.delete(conv)
        session.commit()
        logger.info(f"删除对话: id={conv_id}")
        return True


def add_message(conv_id: int, role: str, content: str, sources=None):
    """存储一条消息。sources 为 list[dict] 或 None。"""
    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
    with SessionLocal() as session:
        msg = ChatMessage(
            conversation_id=conv_id,
            role=role,
            content=content,
            sources_json=sources_json,
        )
        session.add(msg)
        conv = session.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv:
            conv.updated_at = datetime.now()
        session.commit()
        session.refresh(msg)
        return msg


def list_messages(conv_id: int):
    """列出对话的所有消息，按时间正序。"""
    with SessionLocal() as session:
        msgs = (
            session.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return msgs


def update_title(conv_id: int, title: str) -> None:
    """更新对话标题（通常在首条消息后自动设置）。"""
    with SessionLocal() as session:
        conv = session.query(Conversation).filter(Conversation.id == conv_id).first()
        if conv:
            conv.title = title[:200]
            conv.updated_at = datetime.now()
            session.commit()
