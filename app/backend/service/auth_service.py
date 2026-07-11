# -*- coding: utf-8 -*-
"""
认证服务：用户注册、登录、密码校验、token 管理。

使用 hashlib.pbkdf2_hmac 做密码哈希（Python 内置，无需额外依赖），
secrets.token_urlsafe 生成 token。token 存内存，服务重启后需重新登录。
"""
import hashlib
import os
import secrets

from app.backend.db.models import User
from app.backend.db.session import SessionLocal
from app.backend.logger import logger

# 内存 token 存储：{token: user_id}
_token_store: dict = {}


def _hash_password(password: str) -> str:
    """使用 pbkdf2_hmac + 随机 salt 哈希密码。返回 'hash_hex$salt_hex' 格式。"""
    salt = os.urandom(16)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{hash_bytes.hex()}${salt.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """校验密码是否匹配存储的 'hash_hex$salt_hex'。"""
    try:
        hash_hex, salt_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return secrets.compare_digest(hash_bytes.hex(), hash_hex)
    except Exception:
        return False


def _issue_token(user_id: int) -> str:
    """生成 token 并存入内存。"""
    token = secrets.token_urlsafe(32)
    _token_store[token] = user_id
    return token


def register(username: str, password: str):
    """注册新用户。用户名已存在时返回 None。成功返回 (token, user)。"""
    with SessionLocal() as session:
        existing = session.query(User).filter(User.username == username).first()
        if existing is not None:
            return None
        user = User(username=username, password_hash=_hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        token = _issue_token(user.id)
        logger.info(f"用户注册成功: {username} (id={user.id})")
        return token, user


def login(username: str, password: str):
    """用户登录。用户名或密码错误时返回 None。成功返回 (token, user)。"""
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        if user is None or not _verify_password(password, user.password_hash):
            return None
        token = _issue_token(user.id)
        logger.info(f"用户登录成功: {username} (id={user.id})")
        return token, user


def logout(token: str) -> None:
    """注销：从内存中移除 token。"""
    _token_store.pop(token, None)


def get_user_by_token(token: str):
    """根据 token 获取用户对象。token 无效返回 None。"""
    user_id = _token_store.get(token)
    if user_id is None:
        return None
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        return user
