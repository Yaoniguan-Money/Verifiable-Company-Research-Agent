from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.domain.report_limits import MAX_FOLLOWUP_CITATIONS
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_composer import compose_followup_answer
from app.services.answer_pipeline import AnswerContext, AnswerPipeline
from app.services.report_reader_text import REPORT_SECTION_SUMMARY, extract_report_section


@dataclass(frozen=True, slots=True)
class FollowupPayload:
    summary_excerpt: str
    primary_facts_json: str
    ambiguities: list[dict[str, object]] = field(default_factory=list)
    citation_lines: list[str] = field(default_factory=list)
    answer_context: AnswerContext | None = None


class FollowupAnswerService:
    def build_followup_context(
        self,
        *,
        task: ResearchTask,
        message: str,
        report: ReportRead,
        facts: list[ExtractedFact],
        verifications: list[VerificationResult],
    ) -> FollowupPayload:
        fact_reads = [ExtractedFactRead.model_validate(item) for item in facts]
        verification_reads = [
            VerificationResultRead.model_validate(item) for item in verifications
        ]
        verified_ids = {
            item.fact_id
            for item in verification_reads
            if str(getattr(item.status, "value", item.status)) == "verified"
        }
        conflicted_ids = {
            item.fact_id
            for item in verification_reads
            if str(getattr(item.status, "value", item.status)) == "conflicted"
        }
        ctx = AnswerPipeline().build_context(
            company_name=task.company_name,
            question=message,
            verified_facts=[fact for fact in fact_reads if fact.id in verified_ids],
            conflicted_facts=[fact for fact in fact_reads if fact.id in conflicted_ids],
            verifications=verification_reads,
        )
        primary = [
            {
                "claim": fact.claim,
                "metric_name": fact.metric_name,
                "value": fact.value,
                "period": fact.period,
                "source_id": fact.source_id,
                "chunk_id": fact.chunk_id,
            }
            for fact in ctx.primary_facts
        ]
        ambiguities = [
            {
                "metric": item.comparable_metric,
                "period": item.period,
                "values": [
                    {
                        "normalized_value": value.normalized_value,
                        "claim": value.claim,
                        "fact_ids": value.fact_ids,
                        "citation_refs": value.citation_refs,
                    }
                    for value in item.values
                ],
            }
            for item in ctx.ambiguities
        ]
        citations = [
            f"- {fact.source_id}:{fact.chunk_id} {fact.claim}"
            for fact in ctx.primary_facts[:MAX_FOLLOWUP_CITATIONS]
        ]
        summary_excerpt = extract_report_section(report.content, REPORT_SECTION_SUMMARY)
        return FollowupPayload(
            summary_excerpt=summary_excerpt or report.content[:600],
            primary_facts_json=json.dumps(primary, ensure_ascii=False),
            ambiguities=ambiguities,
            citation_lines=citations,
            answer_context=ctx,
        )

    def compose_followup_answer(
        self,
        *,
        task: ResearchTask,
        message: str,
        payload: FollowupPayload,
    ) -> str:
        return compose_followup_answer(
            company_name=task.company_name,
            user_message=message,
            report_summary=payload.summary_excerpt,
            fact_set=None if payload.answer_context is None else _fact_set(payload.answer_context),
            plan=None if payload.answer_context is None else payload.answer_context.plan,
        )


def _fact_set(ctx: AnswerContext):
    from app.services.answer_selection import AnswerFactSet

    return AnswerFactSet(
        primary_facts=ctx.primary_facts,
        context_facts=ctx.optional_context_facts,
        verification_conflicted_count=ctx.verification_conflicted_count,
        metric_ambiguity_count=len(ctx.ambiguities),
        gap_notes=ctx.display_notes,
    )

