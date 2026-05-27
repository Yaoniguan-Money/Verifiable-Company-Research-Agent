from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.schemas.common import TaskStatus
from app.schemas.workflow import WorkflowState
from app.services.workflow_step_executor import WorkflowStepExecutor


def _state() -> WorkflowState:
    return WorkflowState(
        task_id="task_1",
        company_name="测试公司",
        question="测试问题",
        status=TaskStatus.RUNNING,
    )


def _executor() -> WorkflowStepExecutor:
    return WorkflowStepExecutor(
        db=SimpleNamespace(),
        settings=SimpleNamespace(),
        artifacts=SimpleNamespace(),
        search_provider=SimpleNamespace(),
        llm_provider=SimpleNamespace(),
        audit=SimpleNamespace(),
    )


def test_workflow_step_names_order_is_stable() -> None:
    assert WorkflowStepExecutor.WORKFLOW_STEP_NAMES == (
        "CreateResearchTask",
        "CollectSources",
        "ChunkAndIndexSources",
        "ExtractFacts",
        "VerifyFacts",
        "AnalyzeRisks",
        "GenerateReport",
        "ComplianceCheck",
        "SaveResult",
    )


def test_execute_step_appends_success_step() -> None:
    state = _state()
    executor = _executor()

    executor.execute_step(state, "CollectSources", lambda: None)

    assert state.current_step == "CollectSources"
    assert len(state.steps) == 1
    step = state.steps[0]
    assert step.step_name == "CollectSources"
    assert step.success is True
    assert step.message == "ok"
    assert step.error is None
    assert step.started_at is not None
    assert step.finished_at is not None


def test_execute_step_appends_failed_step_and_reraises() -> None:
    state = _state()
    executor = _executor()

    def fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        executor.execute_step(state, "ExtractFacts", fail)

    assert len(state.steps) == 1
    step = state.steps[0]
    assert step.step_name == "ExtractFacts"
    assert step.success is False
    assert step.error == "boom"
    assert step.started_at is not None
    assert step.finished_at is not None


def test_execute_workflow_step_rejects_unknown_step() -> None:
    executor = _executor()

    with pytest.raises(ValueError, match="Unknown workflow step: UnknownStep"):
        executor.execute_workflow_step(
            task=SimpleNamespace(id="task_1"),
            state=_state(),
            step_name="UnknownStep",
        )


def test_run_service_workflow_steps_uses_same_step_name_order() -> None:
    class RecordingExecutor(WorkflowStepExecutor):
        def __init__(self) -> None:
            super().__init__(
                db=SimpleNamespace(),
                settings=SimpleNamespace(),
                artifacts=SimpleNamespace(),
                search_provider=SimpleNamespace(),
                llm_provider=SimpleNamespace(),
                audit=SimpleNamespace(),
            )
            self.executed_steps: list[str] = []

        def execute_workflow_step(self, *, task, state, step_name: str) -> None:
            self.executed_steps.append(step_name)

    executor = RecordingExecutor()

    executor.run_service_workflow_steps(task=SimpleNamespace(id="task_1"), state=_state())

    assert tuple(executor.executed_steps) == WorkflowStepExecutor.WORKFLOW_STEP_NAMES
