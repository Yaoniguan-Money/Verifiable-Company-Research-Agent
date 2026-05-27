"""阶段 1.D：研究任务 API 测试。"""

from __future__ import annotations

import uuid

from app.api.deps import get_research_workflow_service
from app.db.models import Report
from app.db.session import get_db
from app.main import app
from app.providers.llm import MockLLMProvider
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportCreate
from app.services.chat import ChatService
from app.services.research_workflow import ResearchWorkflowService
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

FORBIDDEN_TOKENS = (
    "买入",
    "卖出",
    "目标价",
    "收益承诺",
    "recommendation",
    "expected_return",
    "target_price",
    "buy",
    "sell",
)


def test_create_get_run_report_flow(
    client: TestClient, db: OrmSession
) -> None:
    r1 = client.post(
        "/api/research/tasks",
        json={"company_name": "测试科技", "question": "近三年的研发投入与风险？"},
    )
    assert r1.status_code == 201
    data = r1.json()
    assert "task_id" in data
    assert data.get("status") == "created"
    task_id = data["task_id"]

    r2 = client.get(f"/api/research/tasks/{task_id}")
    assert r2.status_code == 200
    t2 = r2.json()
    assert t2["task_id"] == task_id
    assert t2["company_name"] == "测试科技"
    assert t2["status"] == "created"

    r3 = client.post(f"/api/research/tasks/{task_id}/run")
    assert r3.status_code == 200
    run_data = r3.json()
    assert run_data["task_id"] == task_id
    assert run_data["status"] == "completed"
    assert run_data.get("report_id")
    assert run_data.get("title")

    r4 = client.get(f"/api/research/tasks/{task_id}/report")
    assert r4.status_code == 200
    rep = r4.json()
    assert "content" in rep
    assert "citations" in rep
    assert rep.get("compliance_status")
    assert len(rep["citations"]) >= 1
    assert "核心发现" in rep["content"]
    assert "风险观察" in rep["content"]
    assert "附录" in rep["content"]
    assert "公开资料来源" in rep["content"]
    assert "来源质量摘要" in rep["content"]
    c0 = rep["citations"][0]
    for key in ("source_id", "chunk_id", "url", "title", "retrieved_at"):
        assert c0.get(key) is not None, f"缺少字段 {key}"

    s = client.get(f"/api/sources/{task_id}")
    assert s.status_code == 200
    assert s.json()["task_id"] == task_id
    assert len(s.json()["items"]) >= 1

    f = client.get(f"/api/facts/{task_id}")
    assert f.status_code == 200
    fact_items = f.json()["items"]
    assert len(fact_items) >= 1
    assert all(item.get("source_id") for item in fact_items)
    assert all(item.get("chunk_id") for item in fact_items)
    assert all(item.get("metric_name") is not None for item in fact_items)
    assert all(item.get("period") is not None for item in fact_items)

    v = client.get(f"/api/verification/{task_id}")
    assert v.status_code == 200
    ver_items = v.json()["items"]
    assert len(ver_items) >= 1
    assert all(item.get("fact_id") for item in ver_items)
    assert all(item.get("task_id") == task_id for item in ver_items)
    assert all(item.get("reason") for item in ver_items)
    # 3.E 接入后，不应把所有事实默认标成 verified。
    assert any(item.get("status") != "verified" for item in ver_items)

    for token in ("买入", "目标价", "收益承诺", "recommendation", "建议买入"):
        assert token not in rep["content"]


def test_404_for_unknown_task(client: TestClient) -> None:
    bad_id = str(uuid.uuid4())
    for path in (
        f"/api/research/tasks/{bad_id}",
        f"/api/research/tasks/{bad_id}/report",
        f"/api/sources/{bad_id}",
        f"/api/facts/{bad_id}",
        f"/api/verification/{bad_id}",
    ):
        assert client.get(path).status_code == 404
    assert client.post(f"/api/research/tasks/{bad_id}/run").status_code == 404
    assert (
        client.post("/api/chat", json={"task_id": bad_id, "message": "请总结"})
    ).status_code == 404


def test_compliance_rewrites_injected_violation(db: OrmSession) -> None:
    class ViolationLLM(MockLLMProvider):
        def generate_report(self, *args, **kwargs) -> ReportCreate:
            base = super().generate_report(*args, **kwargs)
            return base.model_copy(
                update={"content": base.content + "\n\n本段为测试注入：建议买入，目标价 99 元；expected_return 10%。"}
            )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_service() -> ResearchWorkflowService:
        return ResearchWorkflowService(db, llm_provider=ViolationLLM())

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_research_workflow_service] = override_service
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/research/tasks",
                json={"company_name": "合规公司", "question": "研究问题"},
            )
            assert r.status_code == 201
            tid = r.json()["task_id"]
            r2 = client.post(f"/api/research/tasks/{tid}/run")
            assert r2.status_code == 200
            r3 = client.get(f"/api/research/tasks/{tid}/report")
            assert r3.status_code == 200
            content = r3.json()["content"]
            for token in FORBIDDEN_TOKENS:
                assert token not in content, f"不应包含: {token}"
    finally:
        app.dependency_overrides.clear()


def test_get_report_applies_output_guardrail_for_legacy_content(db: OrmSession) -> None:
    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_service() -> ResearchWorkflowService:
        return ResearchWorkflowService(db, llm_provider=MockLLMProvider())

    task = ResearchWorkflowService(db).create_research_task(
        company_name="遗留测试公司",
        question="遗留报告读取",
    )
    db.add(
        Report(
            task_id=task.id,
            title="遗留报告",
            content="这是遗留文本：建议买入并加仓。",
            citations=[],
            compliance_status=ComplianceStatus.SKIPPED.value,
        )
    )
    db.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_research_workflow_service] = override_service
    try:
        with TestClient(app) as client:
            r = client.get(f"/api/research/tasks/{task.id}/report")
            assert r.status_code == 200
            body = r.json()
            assert body["compliance_status"] == "blocked"
            assert body["content"]
    finally:
        app.dependency_overrides.clear()


def test_chat_followup_should_return_structured_answer(client: TestClient) -> None:
    created = client.post(
        "/api/research/tasks",
        json={"company_name": "聊天公司", "question": "请总结研发与风险"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    ran = client.post(f"/api/research/tasks/{task_id}/run")
    assert ran.status_code == 200

    chat = client.post(
        "/api/chat",
        json={"task_id": task_id, "message": "请基于当前报告总结关键风险"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["task_id"] == task_id
    assert body["message"]
    assert body["answer"]
    assert body["compliance_status"] in {"passed", "rewritten", "blocked"}
    assert isinstance(body["violations"], list)


def test_chat_violation_question_should_be_blocked(client: TestClient) -> None:
    created = client.post(
        "/api/research/tasks",
        json={"company_name": "聊天公司", "question": "请总结研发与风险"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    ran = client.post(f"/api/research/tasks/{task_id}/run")
    assert ran.status_code == 200

    chat = client.post(
        "/api/chat",
        json={"task_id": task_id, "message": "这家公司现在能买吗？"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["compliance_status"] == "blocked"
    assert "已按合规策略拒绝" in body["answer"]


def test_chat_should_return_404_when_report_missing(client: TestClient) -> None:
    created = client.post(
        "/api/research/tasks",
        json={"company_name": "无报告公司", "question": "先不跑工作流"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    chat = client.post(
        "/api/chat",
        json={"task_id": task_id, "message": "请总结"},
    )
    assert chat.status_code == 404


def test_chat_followup_replaces_ungrounded_provider_answer(db: OrmSession) -> None:
    class UngroundedFollowupLLM(MockLLMProvider):
        def answer_followup(self, *args, **kwargs) -> str:
            return (
                "不过，我可以基于样例公司常规公开信息进行一般性说明，"
                "但这不来自您提到的特定报告。"
            )

    task = ResearchWorkflowService(db).create_research_task(
        company_name="追问公司",
        question="近三年研发变化",
    )
    db.add(
        Report(
            task_id=task.id,
            title="追问公司报告",
            content=(
                "# 追问公司报告\n\n"
                "## 研究问题覆盖情况\n"
                "- 未抽取到研发投入/研发费用事实；报告只能说明当前公开资料证据缺口。\n\n"
                "## 免责声明\n本报告基于公开资料生成，仅用于信息研究，不构成投资建议。"
            ),
            citations=[],
            compliance_status=ComplianceStatus.PASSED.value,
        )
    )
    db.commit()

    result = ChatService(db, llm_provider=UngroundedFollowupLLM()).chat_with_task(
        task_id=task.id,
        message="请说明主要经济来源和风险",
    )

    assert "常规公开信息" not in result.answer
    assert "不来自您提到的特定报告" not in result.answer
    assert "当前报告" in result.answer
    assert "未写入足以直接回答该点的可核对事实" in result.answer
