from __future__ import annotations

from datetime import datetime, timezone

from app.providers.qianfan_llm_provider import QianfanLLMProvider
from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import ComplianceStatus, TaskStatus
from app.schemas.report import ReportRead
from app.schemas.task import ResearchTaskRead


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "风险观察"}}]}


def test_qianfan_request_uses_bearer_authorization(monkeypatch) -> None:
    captured: dict = {}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("app.providers.qianfan_llm_provider.httpx.Client", FakeClient)
    provider = QianfanLLMProvider(
        api_key="unit-test-token",
        base_url="https://example.invalid/v2",
        model="unit-test-model",
        timeout_seconds=12,
    )

    result = provider.analyze_risks("测试公司", "经营风险", [], [])

    assert result == "风险观察"
    assert captured["url"] == "https://example.invalid/v2/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-token"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["json"]["model"] == "unit-test-model"
    assert captured["json"]["stream"] is False
    assert captured["json"]["temperature"] == 0.2
    assert captured["timeout"] == 12


def test_qianfan_extract_facts_returns_empty_when_json_is_invalid(monkeypatch) -> None:
    monkeypatch.setattr(
        QianfanLLMProvider,
        "_chat",
        lambda self, messages, *, max_tokens: "这不是 JSON",
    )
    provider = QianfanLLMProvider(api_key="unit-test-token")
    chunk = EvidenceChunkRead(
        id="chunk-1",
        source_id="source-1",
        task_id="task-1",
        chunk_index=0,
        text="测试公司披露研发投入增加，并提示供应链风险。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    facts = provider.extract_facts("task-1", "测试公司", "研发和风险", [chunk])

    assert facts == []


def test_qianfan_compliance_guardrail_blocks_and_rewrites_violations() -> None:
    provider = QianfanLLMProvider(api_key="unit-test-token")

    blocked_buy = provider.check_compliance("建议买入。")
    blocked_sell = provider.check_compliance("建议卖出。")
    rewritten_target = provider.check_compliance("该公司的目标价可能上调。")
    rewritten_return = provider.check_compliance("这里存在收益承诺和 expected return 预测。")

    assert blocked_buy.status.value == "blocked"
    assert "买入" in blocked_buy.violations
    assert blocked_sell.status.value == "blocked"
    assert "卖出" in blocked_sell.violations
    assert rewritten_target.status.value == "rewritten"
    assert "目标价" in rewritten_target.violations
    assert rewritten_return.status.value == "rewritten"
    assert "收益承诺" in rewritten_return.violations
def test_qianfan_followup_prompt_includes_structured_payload(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_chat_with_system(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> str:
        captured["prompt"] = user_prompt
        return "ok"

    class Payload:
        primary_facts_json = '[{"claim":"2025年研发投入为10亿元"}]'
        ambiguities = [{"metric": "r_and_d", "period": "2025"}]
        citation_lines = ["- source_1:chunk_1 2025年研发投入为10亿元"]

    monkeypatch.setattr(QianfanLLMProvider, "_chat_with_system", fake_chat_with_system)
    provider = QianfanLLMProvider(api_key="unit-test-token")
    now = datetime.now(timezone.utc)

    provider.answer_followup(
        task=ResearchTaskRead(
            id="task-1",
            user_id="user-1",
            company_name="Example Co",
            question="研发投入",
            status=TaskStatus.COMPLETED,
            created_at=now,
            updated_at=now,
        ),
        message="2025年研发投入是多少？",
        report=ReportRead(
            id="report-1",
            task_id="task-1",
            title="report",
            content="## 总结\n已有研发投入信息。",
            citations=[],
            compliance_status=ComplianceStatus.PASSED,
            created_at=now,
        ),
        fact_count=1,
        verification_counts={"verified": 1},
        followup_payload=Payload(),
    )

    assert "followup_facts_json" in captured["prompt"]
    assert "2025年研发投入为10亿元" in captured["prompt"]
    assert "do not say the report lacks" in captured["prompt"]
