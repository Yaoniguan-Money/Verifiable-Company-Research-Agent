from __future__ import annotations

from collections.abc import Callable

from app.db.models import ResearchTask
from app.repositories import ResearchArtifactRepository
from app.schemas.workflow import WorkflowDecision, WorkflowState


class WorkflowAuditService:
    """集中管理 workflow 条件分支和降级决策的审计记录。"""

    def __init__(self, artifacts: ResearchArtifactRepository) -> None:
        self.artifacts = artifacts

    def record_workflow_decision(
        self,
        state: WorkflowState,
        *,
        node: str,
        reason: str,
        message: str,
        task_id: str | None = None,
        status_counts: dict[str, int] | None = None,
    ) -> None:
        state.workflow_decisions.append(
            WorkflowDecision(
                node=node,
                reason=reason,
                message=message,
                task_id=task_id,
                status_counts=status_counts or {},
            )
        )

    def has_extracted_facts(self, task_id: str) -> bool:
        return bool(self.artifacts.list_facts(task_id))

    def record_evidence_gap(
        self,
        *,
        task: ResearchTask,
        state: WorkflowState,
        execute_step: Callable[[WorkflowState, str, Callable[[], None]], None],
    ) -> None:
        def record() -> None:
            self.record_workflow_decision(
                state,
                node="RecordEvidenceGap",
                reason="no_extracted_facts",
                message=(
                    "事实抽取为空，跳过事实验证节点；报告只能说明证据缺口，"
                    "不形成确定性结论。"
                ),
                task_id=task.id,
            )
            state.errors.append("evidence_gap:no_extracted_facts")

        execute_step(state, "RecordEvidenceGap", record)

    def verification_review_required(self, task_id: str) -> bool:
        summary = self.verification_status_summary(task_id)
        conflicted = summary.get("conflicted", 0)
        rejected = summary.get("rejected", 0)
        verified = summary.get("verified", 0)
        insufficient = summary.get("insufficient", 0)
        return bool(conflicted or rejected or (insufficient and not verified))

    def record_verification_risk(
        self,
        *,
        task: ResearchTask,
        state: WorkflowState,
        execute_step: Callable[[WorkflowState, str, Callable[[], None]], None],
    ) -> None:
        def record() -> None:
            summary = self.verification_status_summary(task.id)
            reasons = self.verification_review_reasons(summary)

            self.record_workflow_decision(
                state,
                node="RecordVerificationRisk",
                reason=",".join(reasons) or "verification_review_required",
                message="验证结果存在冲突、拒绝项或缺少已验证事实，报告结论必须保持审慎表达。",
                task_id=task.id,
                status_counts=summary,
            )
            state.errors.append(f"verification_gate:{','.join(reasons)}")

        execute_step(state, "RecordVerificationRisk", record)

    def build_workflow_audit_section(self, state: WorkflowState) -> str:
        decisions = state.workflow_decisions
        if not decisions:
            return ""

        lines = [
            "",
            "",
            "## 附录：处理记录",
            "",
            "以下记录用于解释为什么某些内容没有形成结论。",
        ]
        for item in decisions:
            lines.append(f"- {item.message}")
            if item.status_counts:
                compact = "；".join(
                    f"{self._status_label(key)} {value} 条"
                    for key, value in sorted(item.status_counts.items())
                )
                lines.append(f"- 校验统计：{compact}")
        return "\n".join(lines)

    def verification_status_summary(self, task_id: str) -> dict[str, int]:
        summary: dict[str, int] = {}
        for item in self.artifacts.list_verifications(task_id):
            status = getattr(item.status, "value", str(item.status))
            summary[status] = summary.get(status, 0) + 1
        return summary

    def verification_review_reasons(self, summary: dict[str, int]) -> list[str]:
        reasons: list[str] = []
        if summary.get("conflicted", 0):
            reasons.append("conflicted_facts")
        if summary.get("rejected", 0):
            reasons.append("rejected_facts")
        if summary.get("insufficient", 0) and not summary.get("verified", 0):
            reasons.append("only_insufficient_facts")
        return reasons

    def _status_label(self, status: str) -> str:
        labels = {
            "verified": "已验证",
            "conflicted": "冲突",
            "insufficient": "证据不足",
            "outdated": "过时",
            "rejected": "已排除",
        }
        return labels.get(status, status)
