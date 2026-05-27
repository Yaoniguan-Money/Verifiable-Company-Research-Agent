from __future__ import annotations

from app.db.models import ExtractedFact, Report, Source, VerificationResult
from app.providers.search.local_documents import LocalDocumentSearchProvider
from app.services.research_workflow import ResearchWorkflowService
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession


def test_local_document_search_provider_reads_front_matter(tmp_path) -> None:
    company_dir = tmp_path / "demo"
    company_dir.mkdir()
    (company_dir / "report.md").write_text(
        """---
title: Demo Report
source_type: annual_report
url: https://example.com/report
published_at: 2024-01-01
credibility_score: 0.91
---

2023年研发投入为100亿元。2023年营收为500亿元。
""",
        encoding="utf-8",
    )

    sources = LocalDocumentSearchProvider(str(tmp_path)).search("demo", "研发投入")

    assert len(sources) == 1
    assert sources[0].title == "Demo Report"
    assert sources[0].source_type == "annual_report"
    assert sources[0].credibility_score == 0.91
    assert "研发投入" in sources[0].raw_content


def test_local_document_search_provider_ignores_non_finite_score(tmp_path) -> None:
    company_dir = tmp_path / "demo"
    company_dir.mkdir()
    (company_dir / "report.md").write_text(
        """---
title: Demo Report
credibility_score: NaN
---

2023年研发投入为100亿元。
""",
        encoding="utf-8",
    )

    sources = LocalDocumentSearchProvider(str(tmp_path)).search("demo", "研发投入")

    assert sources[0].credibility_score == 0.8


def test_local_document_search_provider_reads_nested_company_docs(tmp_path) -> None:
    nested = tmp_path / "demo_tech" / "reports"
    nested.mkdir(parents=True)
    (nested / "annual.md").write_text(
        "2023年研发投入为100亿元。2023年净利润为20亿元。",
        encoding="utf-8",
    )

    sources = LocalDocumentSearchProvider(str(tmp_path)).search("demo tech", "净利润")

    assert len(sources) == 1
    assert sources[0].title == "annual"
    assert "净利润" in sources[0].raw_content


def test_workflow_runs_with_dense_local_documents(tmp_path, db: OrmSession) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "annual_report.md").write_text(
        """---
title: Demo Tech 2023 年年度报告摘要
source_type: annual_report
url: https://example.com/demo-tech/annual-report-2023
published_at: 2024-03-28
credibility_score: 0.92
---

2022年研发投入为80亿元，2023年研发投入为100亿元。2023年营收为500亿元，
2023年净利润为40亿元。管理层提示供应链和海外交付存在不确定性。
""",
        encoding="utf-8",
    )
    (company_dir / "announcement.md").write_text(
        """---
title: Demo Tech 2024 半年度经营公告
source_type: announcement
url: https://example.com/demo-tech/announcement-2024-h1
published_at: 2024-08-20
credibility_score: 0.86
---

2024年上半年营收为280亿元，净利润为18亿元。公告称公司继续增加研发投入，
但没有披露完整年度研发投入金额。
""",
        encoding="utf-8",
    )
    (company_dir / "industry_news.md").write_text(
        """---
title: 行业媒体关于 Demo Tech 的跟踪报道
source_type: news
url: https://example.com/news/demo-tech
published_at: 2024-09-01
credibility_score: 0.68
---

行业媒体估算2023年营收为520亿元，与公司年度报告披露口径存在差异。
报道同时提到海外项目回款周期和核心零部件供应稳定性仍需跟踪。
""",
        encoding="utf-8",
    )

    service = ResearchWorkflowService(
        db=db,
        search_provider=LocalDocumentSearchProvider(str(tmp_path)),
    )
    task = service.create_research_task(
        company_name="demo tech",
        question="请分析研发投入、营收变化、数据冲突和主要经营风险。",
    )

    outcome = service.run_workflow(task.id)

    assert outcome.success
    assert db.scalar(select(Source).where(Source.task_id == task.id).limit(1)) is not None
    facts = db.scalars(select(ExtractedFact).where(ExtractedFact.task_id == task.id)).all()
    verifications = db.scalars(
        select(VerificationResult).where(VerificationResult.task_id == task.id)
    ).all()
    report = db.scalar(select(Report).where(Report.task_id == task.id))
    assert len(facts) >= 6
    assert any(f.period == "2022" and f.value == "80亿元" for f in facts)
    assert any(f.period == "2023" and f.value == "100亿元" for f in facts)
    assert any(getattr(v.status, "value", str(v.status)) == "conflicted" for v in verifications)
    assert report is not None
    assert len(report.citations or []) >= 3
