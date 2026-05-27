from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.research import ResearchArtifactRepository
from app.schemas.common import SourceType
from app.schemas.source import SourceCreate
from sqlalchemy.orm import Session as OrmSession


def test_add_sources_infers_disclosure_kind(db: OrmSession) -> None:
    repo = ResearchArtifactRepository(db)
    rows = repo.add_sources(
        task_id="task_1",
        sources=[
            SourceCreate(
                task_id="task_1",
                title="测试公司2025年年度报告",
                url="https://example.com/report.pdf",
                source_type=SourceType.ANNUAL_REPORT,
                published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                retrieved_at=datetime.now(timezone.utc),
                raw_content="annual report",
                credibility_score=0.9,
            ),
            SourceCreate(
                task_id="task_1",
                title="媒体报道",
                url="https://example.com/news",
                source_type=SourceType.NEWS,
                published_at=None,
                retrieved_at=datetime.now(timezone.utc),
                raw_content="news",
                credibility_score=0.5,
            ),
        ],
    )

    assert rows[0].source_metadata["disclosure_kind"] == "annual"
    assert rows[1].source_metadata["disclosure_kind"] == "media"

