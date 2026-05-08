"""File-backed SQLite workflow integration test.

目的：避免「仅内存库全绿、真实/文件开发库失败」的回归。使用 pytest 临时目录下
的独立 ``*.db`` 文件，跑完整 create → run 链路并核对各表行与 citations。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.db import session as db_session
from app.db.init_db import create_all_tables, ensure_default_user
from app.db.models import (
    EvidenceChunk,
    ExtractedFact,
    Report,
    ResearchTask,
    Source,
    VerificationResult,
)
from app.services.research_workflow import ResearchWorkflowService


@pytest.fixture
def file_sqlite_env(tmp_path: Path) -> Generator[Path, None, None]:
    """切换到文件型 SQLite，测试结束后恢复 conftest 使用的内存库配置。"""
    db_file = tmp_path / "workflow_integration.db"
    url = f"sqlite:///{db_file.as_posix()}"
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    db_session.reset_engine()
    create_all_tables()
    try:
        yield db_file
    finally:
        if old is not None:
            os.environ["DATABASE_URL"] = old
        else:
            os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        get_settings.cache_clear()
        db_session.reset_engine()
        create_all_tables()


def test_full_mock_chain_persists_on_file_sqlite(file_sqlite_env: Path) -> None:
    db = db_session.SessionLocal()
    try:
        ensure_default_user(db)
        svc = ResearchWorkflowService(db)
        task = svc.create_research_task(
            company_name="文件库集成公司",
            question="公开资料下的研发与风险？",
        )
        out = svc.run_workflow(task.id)
        assert out.success, f"run_workflow 应成功: {out.error}"
        rpt = svc.get_report(task.id)
        assert rpt is not None
        assert len(rpt.citations) >= 1
        c0 = rpt.citations[0]
        assert c0.source_id and c0.chunk_id and c0.url and c0.title and c0.retrieved_at

        assert db.query(ResearchTask).filter(ResearchTask.id == task.id).one_or_none() is not None
        assert db.query(Source).filter(Source.task_id == task.id).count() >= 1
        assert db.query(EvidenceChunk).filter(EvidenceChunk.task_id == task.id).count() >= 1
        assert db.query(ExtractedFact).filter(ExtractedFact.task_id == task.id).count() >= 1
        assert (
            db.query(VerificationResult).filter(VerificationResult.task_id == task.id).count() >= 1
        )
        assert db.query(Report).filter(Report.task_id == task.id).one_or_none() is not None
    finally:
        db.close()
    # 确认数据库文件在磁盘上（StaticPool/文件型 sqlite 会创建）
    assert file_sqlite_env.is_file() and file_sqlite_env.stat().st_size > 0
