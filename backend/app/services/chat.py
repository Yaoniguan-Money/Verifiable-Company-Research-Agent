from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.providers.llm.base import ComplianceCheckResult
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportRead
from app.services.chat_grounding import GroundedFollowupAnswerBuilder
from app.services.chat_guardrail import ChatGuardrailService
from app.services.chat_memory import ChatMemoryService
from app.services.report_output import ReportOutputService

if TYPE_CHECKING:
    from fastapi import BackgroundTasks


@dataclass(frozen=True, slots=True)
class ChatResult:
    task_id: str
    message: str
    answer: str
    compliance_status: ComplianceStatus
    violations: list[str]


class ChatService:
    """Minimal report-grounded follow-up service.

    This keeps chat assembly out of ResearchWorkflowService, which should stay
    focused on the research pipeline.
    """

    def __init__(self, db: Session, llm_provider: LLMProvider | None = None) -> None:
        self.db = db
        self.llm_provider = llm_provider or ProviderFactory().create_llm_provider()
        self.guardrail = ChatGuardrailService(self.llm_provider)
        self.grounding = GroundedFollowupAnswerBuilder()
        self.tasks = ResearchTaskRepository(db)
        self.artifacts = ResearchArtifactRepository(db)

    def chat_with_task(
        self,
        *,
        task_id: str,
        message: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> ChatResult:
        task = self._get_task(task_id)
        if task is None:
            raise ValueError("task not found")

        report = self._get_report_for_output(task_id)
        if report is None:
            raise ValueError("report not generated")

        user_intent_check = self.guardrail.guard_user_message(message)
        if not user_intent_check.is_compliant:
            result = self._blocked_result(task_id, message, user_intent_check)
            self._record_memory_turn(
                task=task,
                message=message,
                answer=result.answer,
                background_tasks=background_tasks,
            )
            return result

        facts = self._list_facts(task_id)
        verifications = self._list_verifications(task_id)
        draft_answer = self._build_answer(
            task=task,
            message=message,
            report=report,
            fact_count=len(facts),
            verification_counts=self._count_verification_statuses(verifications),
        )
        verification_counts = self._count_verification_statuses(verifications)
        draft_answer = self.grounding.ensure_report_grounded_answer(
            answer=draft_answer,
            task=task,
            message=message,
            report=report,
            facts=facts,
            verifications=verifications,
            verification_counts=verification_counts,
        )
        final_check = self.guardrail.guard_assistant_output(draft_answer)
        result = ChatResult(
            task_id=task_id,
            message=message,
            answer=final_check.rewritten_text or draft_answer,
            compliance_status=final_check.status,
            violations=final_check.violations,
        )
        self._record_memory_turn(
            task=task,
            message=message,
            answer=result.answer,
            background_tasks=background_tasks,
        )
        return result

    def _blocked_result(
        self,
        task_id: str,
        message: str,
        check: ComplianceCheckResult,
    ) -> ChatResult:
        return ChatResult(
            task_id=task_id,
            message=message,
            answer=check.rewritten_text or "The request was blocked by the compliance guardrail.",
            compliance_status=check.status,
            violations=check.violations,
        )

    def _get_task(self, task_id: str) -> ResearchTask | None:
        return self.tasks.get(task_id)

    def _record_memory_turn(
        self,
        *,
        task: ResearchTask,
        message: str,
        answer: str,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        ChatMemoryService(self.db).record_turn_for_task(
            task=task,
            user_message=message,
            assistant_answer=answer,
            background_tasks=background_tasks,
        )

    def _get_report_for_output(self, task_id: str) -> ReportRead | None:
        return ReportOutputService(self.db, self.llm_provider).get_report_for_output(task_id)

    def _list_facts(self, task_id: str) -> list[ExtractedFact]:
        return self.artifacts.list_facts(task_id)

    def _list_verifications(self, task_id: str) -> list[VerificationResult]:
        return self.artifacts.list_verifications(task_id)

    def _count_verification_statuses(
        self,
        verifications: list[VerificationResult],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in verifications:
            key = getattr(item.status, "value", str(item.status))
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _build_answer(
        self,
        *,
        task: ResearchTask,
        message: str,
        report: ReportRead,
        fact_count: int,
        verification_counts: dict[str, int],
    ) -> str:
        provider_answer = getattr(self.llm_provider, "answer_followup", None)
        if callable(provider_answer):
            return str(
                provider_answer(
                    task=task,
                    message=message,
                    report=report,
                    fact_count=fact_count,
                    verification_counts=verification_counts,
                )
            )
        report_brief = report.content.strip().replace("\n", " ")
        if len(report_brief) > 220:
            report_brief = report_brief[:220] + "..."

        return (
            f"基于当前任务“{task.company_name}”的报告与证据，最小追问回答如下：\n"
            f"- 用户问题：{message}\n"
            f"- 报告摘要：{report_brief}\n"
            f"- 已抽取事实：{fact_count} 条；验证状态统计：{verification_counts}\n"
            "- 如需进一步分析，请指定指标、期间、来源或风险点。"
        )
