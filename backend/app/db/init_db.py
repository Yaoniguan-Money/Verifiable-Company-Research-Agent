"""数据库初始化与默认用户引导。

当前 public release 使用 ``Base.metadata.create_all`` 支持本地 SQLite 演示和测试。
如果后续接入生产数据库，应迁移到 Alembic 管理 schema 变更。

本模块在应用启动时被 ``main.create_app`` 调用一次，幂等安全（多次调用不会重复建表/插数据）。
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session as OrmSession

# 触发 models 子模块 import，让 Base.metadata 收齐所有表
from app.db import models  # noqa: F401  (re-export side effect)

# 注意：必须 import 整个 ``session`` 模块而不是 from-import；
# 否则 reset_engine() 后这里仍持有旧 engine / SessionLocal。
from app.db import session as db_session
from app.db.base import Base
from app.db.models import User

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "default_user"


def create_all_tables() -> None:
    """根据当前 Base.metadata 建表（已存在的表跳过）。"""
    Base.metadata.create_all(bind=db_session.engine)
    ensure_lightweight_schema_updates()
    logger.info("DB tables created (or already exist).")


def ensure_lightweight_schema_updates(bind: Engine | None = None) -> None:
    """在 Alembic 接入前，只处理向后兼容的小字段补齐。"""
    engine = bind or db_session.engine
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "verification_results" in table_names:
        columns = {column["name"] for column in inspector.get_columns("verification_results")}
        if "reason_code" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE verification_results ADD COLUMN reason_code VARCHAR(64)"))
    if "sources" in table_names:
        columns = {column["name"] for column in inspector.get_columns("sources")}
        if "source_metadata" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE sources ADD COLUMN source_metadata JSON"))
    if "user_memories" in table_names:
        columns = {column["name"] for column in inspector.get_columns("user_memories")}
        if "memory_layer" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE user_memories "
                        "ADD COLUMN memory_layer VARCHAR(16) NOT NULL DEFAULT 'warm'"
                    )
                )


def ensure_default_user(db: OrmSession) -> User:
    """若 default_user 不存在则创建并返回；存在则直接返回。

    当前 release 不包含登录系统，所有 task 默认绑定到该用户。
    """
    user = db.scalar(select(User).where(User.username == DEFAULT_USERNAME))
    if user is None:
        user = User(username=DEFAULT_USERNAME, email=None)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Default user bootstrapped: id=%s", user.id)
    return user


def init_db() -> None:
    """应用启动时调用：建表 + 默认用户。幂等。"""
    create_all_tables()
    with db_session.SessionLocal() as db:
        ensure_default_user(db)


def get_default_user(db: OrmSession) -> User:
    """运行时获取默认用户（API 层使用）。

    若被意外删除则即时重建，避免请求失败。
    """
    return ensure_default_user(db)
