"""在默认 data/dev.db 上验证主链路（create -> run -> report + citations + 表行）。

与 ORM/文档一致：表 ``evidence_chunks`` 的 JSON 列名为 ``chunk_metadata``；HTTP 报告中的
citations 使用 Schema 的 ``metadata`` 等对外字段，不要求改列名。

项目根目录执行（PowerShell）：
  $env:PYTHONPATH = "backend"
  .\\.venv\\Scripts\\python.exe scripts\\verify_devdb_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATABASE_URL"] = "sqlite:///./data/dev.db"
os.environ.setdefault("APP_ENV", "dev")

from app.core.config import get_settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    EvidenceChunk,
    ExtractedFact,
    Report,
    ResearchTask,
    Source,
    VerificationResult,
)
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

get_settings.cache_clear()
db_session.reset_engine()
init_db()

if __name__ == "__main__":
    with TestClient(app) as client:
        r = client.post(
            "/api/research/tasks",
            json={"company_name": "dev.db smoke", "question": "主链路是否可运行？"},
        )
        assert r.status_code == 201, r.text
        tid = r.json()["task_id"]
        r2 = client.post(f"/api/research/tasks/{tid}/run")
        assert r2.status_code == 200, r2.text
        r3 = client.get(f"/api/research/tasks/{tid}/report")
        assert r3.status_code == 200, r3.text
        body = r3.json()
        cits = body.get("citations") or []
        assert len(cits) >= 1, "报告应含至少 1 条 citation"
        print("OK API:", "task_id=", tid, "citations=", len(cits))

    s = db_session.SessionLocal()
    try:
        assert s.query(ResearchTask).filter(ResearchTask.id == tid).one_or_none() is not None
        assert s.query(Source).filter(Source.task_id == tid).count() >= 1
        assert s.query(EvidenceChunk).filter(EvidenceChunk.task_id == tid).count() >= 1
        assert s.query(ExtractedFact).filter(ExtractedFact.task_id == tid).count() >= 1
        assert s.query(VerificationResult).filter(VerificationResult.task_id == tid).count() >= 1
        assert s.query(Report).filter(Report.task_id == tid).one_or_none() is not None
    finally:
        s.close()
    print("OK DB: 六类实体均已落库")
