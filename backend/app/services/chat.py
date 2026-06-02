from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.db.models import ResearchTask, VerificationResult
from app.domain.report_limits import FALLBACK_REPORT_BRIEF_LIMIT
from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.providers.llm.base import ComplianceCheckResult
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportRead
from app.services.chat_grounding import GroundedFollowupAnswerBuilder
from app.services.chat_guardrail import ChatGuardrailService
from app.services.chat_memory import ChatMemoryService
from app.services.followup_answer import FollowupAnswerService, FollowupPayload
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
    """报告追问服务。

    把追问相关逻辑（合规护栏、grounding、记忆）从 ``ResearchWorkflowService`` 里拆出来，
    使 workflow facade 专心于研究流水线本身。
    """

    def __init__(self, db: Session, llm_provider: LLMProvider | None = None) -> None:
        self.db = db
        self.llm_provider = llm_provider or ProviderFactory().create_llm_provider()
        self.guardrail = ChatGuardrailService(self.llm_provider)
        self.grounding = GroundedFollowupAnswerBuilder()
        self.followup = FollowupAnswerService()
        self.tasks = ResearchTaskRepository(db)
        self.artifacts = ResearchArtifactRepository(db)

    def chat_with_task(
        self,
        *,
        task_id: str,
        message: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> ChatResult:
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError("task not found")

        report = self._get_report_for_output(task_id)
        if report is None:
            raise ValueError("report not generated")

        # 1) 输入侧合规：用户问题明显涉及投资建议时直接拒绝并落记忆。
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

        # 2) 生成答复 + grounding 校验：必要时强行回到报告内证据。
        facts = self.artifacts.list_facts(task_id)
        verifications = self.artifacts.list_verifications(task_id)
        verification_counts = self._count_verification_statuses(verifications)
        followup_payload = self.followup.build_followup_context(
            task=task,
            message=message,
            report=report,
            facts=facts,
            verifications=verifications,
        )
        draft_answer = self._build_answer(
            task=task,
            message=message,
            report=report,
            fact_count=len(facts),
            verification_counts=verification_counts,
            followup_payload=followup_payload,
        )
        draft_answer = self.grounding.ensure_report_grounded_answer(
            answer=draft_answer,
            task=task,
            message=message,
            report=report,
            facts=facts,
            verifications=verifications,
            verification_counts=verification_counts,
        )

        # 3) 输出侧合规：把最终答复再过一次规则层。
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
            answer=check.rewritten_text or "已按合规策略拒绝。",
            compliance_status=check.status,
            violations=check.violations,
        )

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
        return ReportOutputService(self.db, self.llm_provider).get_report(task_id)

    @staticmethod
    def _count_verification_statuses(
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
        followup_payload: FollowupPayload | None = None,
    ) -> str:
        """有 ``answer_followup`` 的 provider 走 LLM；否则用 deterministic 模板兜底。"""
        provider_answer = getattr(self.llm_provider, "answer_followup", None)
        if callable(provider_answer):
            return str(
                provider_answer(
                    task=task,
                    message=message,
                    report=report,
                    fact_count=fact_count,
                    verification_counts=verification_counts,
                    followup_payload=followup_payload,
                )
            )

        if followup_payload and (
            (
                followup_payload.answer_context is not None
                and followup_payload.answer_context.primary_facts
            )
            or followup_payload.ambiguities
        ):
            return self.followup.compose_followup_answer(
                task=task,
                message=message,
                payload=followup_payload,
            )

        report_brief = report.content.strip().replace("\n", " ")
        if len(report_brief) > FALLBACK_REPORT_BRIEF_LIMIT:
            report_brief = report_brief[:FALLBACK_REPORT_BRIEF_LIMIT] + "..."
        from app.services.report_reader_text import extract_report_section

        summary = extract_report_section(report.content, "总结")
        if summary:
            return (
                f"关于「{message}」：{summary} "
                "更完整的条目与来源见当前报告正文。"
            )
        return (
            f"关于「{message}」，根据当前「{task.company_name}」研究报告：{report_brief} "
            "若需某一年份或具体指标，可在报告中查看「核心发现」与对应来源。"
        )
