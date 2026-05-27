from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from app.schemas.common import TaskStatus
from app.schemas.workflow import WorkflowState
from app.services.workflow_audit import WorkflowAuditService


class FakeArtifacts:
    def __init__(self, *, facts=None, verification_statuses=None) -> None:
        self._facts = facts or []
        self._verification_statuses = verification_statuses or []

    def list_facts(self, task_id: str):
        return self._facts

    def list_verifications(self, task_id: str):
        return [SimpleNamespace(status=status) for status in self._verification_statuses]


def _state() -> WorkflowState:
    return WorkflowState(
        task_id="task_1",
        company_name="测试公司",
        question="测试问题",
        status=TaskStatus.RUNNING,
    )


def _execute_step(state: WorkflowState, step_name: str, fn: Callable[[], None]) -> None:
    assert step_name == "RecordEvidenceGap"
    fn()


def test_record_workflow_decision_appends_decision_to_state() -> None:
    state = _state()
    service = WorkflowAuditService(FakeArtifacts())

    service.record_workflow_decision(
        state,
        node="AnalyzeRisks",
        reason="llm_risk_analysis_degraded",
        message="降级为规则摘要",
        task_id="task_1",
        status_counts={"insufficient": 2},
    )

    assert len(state.workflow_decisions) == 1
    decision = state.workflow_decisions[0]
    assert decision.node == "AnalyzeRisks"
    assert decision.reason == "llm_risk_analysis_degraded"
    assert decision.message == "降级为规则摘要"
    assert decision.task_id == "task_1"
    assert decision.status_counts == {"insufficient": 2}


def test_record_evidence_gap_records_no_extracted_facts() -> None:
    state = _state()
    task = SimpleNamespace(id="task_1")
    service = WorkflowAuditService(FakeArtifacts())

    service.record_evidence_gap(task=task, state=state, execute_step=_execute_step)

    assert state.workflow_decisions[0].node == "RecordEvidenceGap"
    assert state.workflow_decisions[0].reason == "no_extracted_facts"
    assert "evidence_gap:no_extracted_facts" in state.errors


@pytest.mark.parametrize(
    "statuses",
    [
        ["conflicted"],
        ["rejected"],
        ["insufficient"],
    ],
)
def test_verification_review_required_for_risky_statuses(statuses: list[str]) -> None:
    service = WorkflowAuditService(FakeArtifacts(verification_statuses=statuses))

    assert service.verification_review_required("task_1") is True


def test_verification_review_required_false_when_verified() -> None:
    service = WorkflowAuditService(FakeArtifacts(verification_statuses=["verified", "insufficient"]))

    assert service.verification_review_required("task_1") is False


def test_build_workflow_audit_section_renders_decisions() -> None:
    state = _state()
    service = WorkflowAuditService(FakeArtifacts())
    service.record_workflow_decision(
        state,
        node="RecordVerificationRisk",
        reason="conflicted_facts",
        message="验证结果存在冲突",
        status_counts={"conflicted": 1},
    )

    section = service.build_workflow_audit_section(state)

    assert "## 附录：处理记录" in section
    assert "验证结果存在冲突" in section
    assert "冲突 1 条" in section
    assert "conflicted_facts" not in section


def test_build_workflow_audit_section_returns_empty_without_decisions() -> None:
    service = WorkflowAuditService(FakeArtifacts())

    assert service.build_workflow_audit_section(_state()) == ""
