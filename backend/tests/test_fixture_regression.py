from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.common import SOURCE_LAYER_METADATA_KEY, SourceLayer
from app.schemas.fact import ExtractedFactRead
from app.services.answer_pipeline import AnswerPipeline
from app.services.fact_verification import FactVerificationService

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _fact(item: dict, idx: int, task_id: str = "task_1") -> ExtractedFactRead:
    return ExtractedFactRead(
        id=f"fact_{idx}",
        task_id=task_id,
        claim=item["claim"],
        metric_name=item.get("metric_name"),
        value=item.get("value"),
        period=item.get("period"),
        source_id=item.get("source_id") or f"source_{idx}",
        chunk_id=f"chunk_{idx}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def test_profit_fixture_keeps_rd_out_of_optional_context() -> None:
    raw = _load("sample_consumer_2025_profit.json")
    facts = [_fact(item, idx) for idx, item in enumerate(raw["facts"], start=1)]
    verified = [fact for fact, item in zip(facts, raw["facts"], strict=False) if item["status"] == "verified"]
    conflicted = [fact for fact, item in zip(facts, raw["facts"], strict=False) if item["status"] == "conflicted"]

    ctx = AnswerPipeline().build_context(
        company_name=raw["company_name"],
        question=raw["question"],
        verified_facts=verified,
        conflicted_facts=conflicted,
        verifications=[],
    )

    assert [fact.metric_name for fact in ctx.primary_facts] == ["net_profit_parent"]
    assert ctx.optional_context_facts == []


def test_rd_fixture_keeps_recent_window_focused() -> None:
    raw = _load("sample_newenergy_rd_window.json")
    facts = [_fact(item, idx) for idx, item in enumerate(raw["facts"], start=1)]

    ctx = AnswerPipeline().build_context(
        company_name=raw["company_name"],
        question=raw["question"],
        verified_facts=facts,
        verifications=[],
    )

    assert ctx.primary_facts
    assert all("R&D" in (fact.metric_name or "") for fact in ctx.primary_facts)
    assert ctx.primary_facts[0].period == "2025"


def test_synthetic_single_source_conflict_fixture_reason_code() -> None:
    raw = _load("synthetic_single_source_conflict.json")
    facts = [_fact(item, idx) for idx, item in enumerate(raw["facts"], start=1)]

    out = FactVerificationService().verify_facts(
        task_id="task_1",
        facts=facts,
        source_context={
            "official_pdf_1": (
                None,
                0.92,
                {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value},
            )
        },
    )

    assert {item.status.value for item in out.results} == {"conflicted"}
    assert {item.reason_code for item in out.results} == {"same_period_value_divergence"}

