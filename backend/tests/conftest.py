"""测试公共 fixtures。

策略：
- 测试统一使用 ``sqlite:///:memory:``，与开发库隔离。
- 通过 monkeypatch 改 ``DATABASE_URL`` 后调 ``reset_engine()``，让模块级 engine 重建。
- 每个测试函数独享一个事务化 Session，结束自动回滚。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session as OrmSession


@pytest.fixture(scope="session", autouse=True)
def _use_inmemory_sqlite(tmp_path_factory) -> None:
    """整个测试会话切换到内存 SQLite。"""
    import os

    # 注意：要在 import session 之前把环境变量设置好
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["APP_ENV"] = "test"
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["SEARCH_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["VECTOR_STORE"] = "in_memory"
    os.environ["HYBRID_RETRIEVAL_ENABLED"] = "false"
    os.environ["MULTI_AGENT_ENABLED"] = "false"
    os.environ["WORKFLOW_ENGINE"] = "langgraph"

    # 强制 settings 重建
    from app.core.config import get_settings

    get_settings.cache_clear()

    # 重建 engine
    from app.db import session as db_session

    db_session.reset_engine()

    # 建表
    from app.db.init_db import create_all_tables

    create_all_tables()


def _apply_test_provider_env() -> None:
    """每轮测试强制 mock 配置，避免 monkeypatch.delenv 后回退到本地 .env。"""
    import os

    from app.core.config import get_settings

    os.environ["APP_ENV"] = "test"
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["SEARCH_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["VECTOR_STORE"] = "in_memory"
    os.environ["HYBRID_RETRIEVAL_ENABLED"] = "false"
    os.environ["MULTI_AGENT_ENABLED"] = "false"
    os.environ["WORKFLOW_ENGINE"] = "langgraph"
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_provider_settings() -> Generator[None, None, None]:
    _apply_test_provider_env()
    yield
    _apply_test_provider_env()


@pytest.fixture
def client(db: OrmSession):
    """HTTP 测试客户端：覆盖 ``get_db``，与 ``db`` fixture 共享同一 Session。"""
    from app.db.session import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def db() -> Generator[OrmSession, None, None]:
    """每个测试一个 Session，自动回滚保证隔离。

    注意：必须通过 ``db_session.SessionLocal`` 访问，而不是 from-import；
    因为 ``reset_engine()`` 会替换 ``SessionLocal`` 模块属性，from-import 会拿到旧值。
    """
    from app.db import session as db_session

    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
