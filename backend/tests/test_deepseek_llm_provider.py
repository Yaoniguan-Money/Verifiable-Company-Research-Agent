from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from app.providers.llm.deepseek_provider import DeepSeekLLMProvider
from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import ComplianceStatus, TaskStatus
from app.schemas.report import ReportRead
from app.schemas.task import ResearchTaskRead


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_deepseek_empty_content_with_reasoning_has_actionable_error(monkeypatch) -> None:
    secret = "test-only-placeholder"
    reasoning = "internal reasoning should not be returned"

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeResponse:
            return _FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": "",
                                "reasoning_content": reasoning,
                            },
                        }
                    ]
                }
            )

    monkeypatch.setattr("app.providers.llm.deepseek_provider.httpx.Client", FakeClient)
    provider = DeepSeekLLMProvider(api_key=secret, model="deepseek-v4-flash")

    with pytest.raises(RuntimeError) as exc_info:
        provider.analyze_risks("Example Co", "Summarize operating risks.", [], [])

    message = str(exc_info.value)
    assert (
        "DeepSeek returned reasoning_content but no final message.content; "
        "use deepseek-chat for smoke tests or increase max_tokens."
    ) in message
    assert secret not in message
    assert "Authorization" not in message
    assert "Bearer" not in message
    assert reasoning not in message


def test_deepseek_request_uses_bearer_authorization(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _FakeResponse({"choices": [{"message": {"content": "risk note"}}]})

    monkeypatch.setattr("app.providers.llm.deepseek_provider.httpx.Client", FakeClient)
    provider = DeepSeekLLMProvider(
        api_key="unit-test-token",
        base_url="https://example.invalid",
        model="deepseek-chat",
        timeout_seconds=11,
    )

    result = provider.analyze_risks("Example Co", "Summarize operating risks.", [], [])

    assert result == "risk note"
    assert captured["url"] == "https://example.invalid/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-token"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["json"]["stream"] is False
    assert captured["json"]["temperature"] == 0.2
    assert captured["timeout"] == 11


def test_deepseek_extract_facts_parses_strict_json_and_keeps_traceability(monkeypatch) -> None:
    chunk = EvidenceChunkRead(
        id="chunk-1",
        source_id="source-1",
        task_id="task-1",
        chunk_index=0,
        text="样例公司2024年营业收入为100亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        DeepSeekLLMProvider,
        "_chat",
        lambda self, prompt, *, max_tokens: (
            '{"facts":['
            '{"claim":"2024年营业收入为100亿元","metric_name":"revenue",'
            '"value":"100亿元","period":"2024","source_id":"source-1",'
            '"chunk_id":"chunk-1","confidence":0.81},'
            '{"claim":"伪造事实","metric_name":"revenue","value":"1亿元",'
            '"period":"2024","source_id":"bad-source","chunk_id":"bad-chunk","confidence":0.9}'
            "]} "
        ),
    )
    provider = DeepSeekLLMProvider(api_key="unit-test-token")

    facts = provider.extract_facts("task-1", "样例公司", "近三年收入变化", [chunk])

    assert len(facts) == 1
    assert facts[0].claim == "2024年营业收入为100亿元"
    assert facts[0].source_id == "source-1"
    assert facts[0].chunk_id == "chunk-1"


def test_deepseek_provider_example_uses_chat_model() -> None:
    template = Path(__file__).resolve().parents[2] / ".env.providers.example"
    template = template.read_text(encoding="utf-8")

    assert "DEEPSEEK_MODEL=deepseek-chat" in template


def test_deepseek_followup_prompt_includes_structured_payload(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_chat(self, prompt: str, *, max_tokens: int, **kwargs) -> str:
        captured["prompt"] = prompt
        return "ok"

    class Payload:
        primary_facts_json = '[{"claim":"2025年研发投入为10亿元"}]'
        ambiguities = [{"metric": "r_and_d", "period": "2025"}]
        citation_lines = ["- source_1:chunk_1 2025年研发投入为10亿元"]

    monkeypatch.setattr(DeepSeekLLMProvider, "_chat", fake_chat)
    provider = DeepSeekLLMProvider(api_key="unit-test-token")
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
