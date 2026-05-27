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


# 向后兼容补齐列表：早期版本的 SQLite 数据库可能缺这些字段，
# 升级到当前版本时一次性补齐，避免线上回归出错。
_LIGHTWEIGHT_COLUMN_ADDITIONS: tuple[tuple[str, str, str], ...] = (
    ("verification_results", "reason_code", "VARCHAR(64)"),
    ("sources", "source_metadata", "JSON"),
    ("user_memories", "memory_layer", "VARCHAR(16) NOT NULL DEFAULT 'warm'"),
)


def ensure_lightweight_schema_updates(bind: Engine | None = None) -> None:
    """Alembic 接入前的过渡：检测缺失字段并 ``ALTER TABLE`` 补齐。

    Alembic 已可用的环境会通过 ``USE_ALEMBIC_ON_STARTUP=true`` 走正式迁移路径；
    本函数只是给本地 SQLite 用户的兼容层。
    """
    engine = bind or db_session.engine
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    for table, column, column_type in _LIGHTWEIGHT_COLUMN_ADDITIONS:
        if table not in table_names:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        if column in existing_cols:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


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


def run_alembic_migrations() -> None:
    """执行 Alembic 升级到 head（仅 PostgreSQL 等生产库推荐）。"""
    from alembic import command
    from alembic.config import Config

    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied.")


def init_db() -> None:
    """应用启动时调用：建表 + 默认用户。幂等。"""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.use_alembic_on_startup and settings.database_url.startswith("postgresql"):
        try:
            run_alembic_migrations()
        except Exception as exc:
            logger.warning("Alembic 迁移失败，回退 create_all: %s", exc)
            create_all_tables()
    else:
        create_all_tables()
    with db_session.SessionLocal() as db:
        ensure_default_user(db)


def get_default_user(db: OrmSession) -> User:
    """运行时获取默认用户（API 层使用）。

    若被意外删除则即时重建，避免请求失败。
    """
    return ensure_default_user(db)
