"""Engine / SessionLocal / FastAPI 依赖。

跨数据库注意事项：
- SQLite 必须 ``check_same_thread=False`` 才能在 FastAPI 多线程环境下使用。
- PostgreSQL 不需要该参数。
- 这里通过 URL 前缀判断，避免业务代码出现 if 分支。
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url

    connect_args: dict = {}
    engine_kwargs: dict = {
        "echo": settings.db_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

        if ":memory:" in url:
            # 内存 SQLite：必须用 StaticPool 让所有连接共享同一份内存库，
            # 否则 fixture 建的表在测试中看不到。
            engine_kwargs["poolclass"] = StaticPool
        else:
            # 文件型 SQLite：确保父目录存在
            # sqlite:///./data/dev.db -> ./data/dev.db
            db_file_part = url.split("///", 1)[-1]
            db_path = Path(db_file_part)
            db_path.parent.mkdir(parents=True, exist_ok=True)

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


# 模块级单例。测试中可通过 reset_engine() 重建。
engine: Engine = _build_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def reset_engine() -> None:
    """测试钩子：重建 engine + SessionLocal（在切换 DATABASE_URL 后调用）。"""
    global engine, SessionLocal
    engine.dispose()
    engine = _build_engine()
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个 Session，结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
