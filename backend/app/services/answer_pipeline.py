from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.schemas.fact import ExtractedFactRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_composer import compose_report_answer
from app.services.answer_selection import AnswerFactSet, select_facts_for_answer
from app.services.fact_metric_normalization import FactMetricNormalizer
from app.services.fact_value_normalization import FactValueNormalizer
from app.services.question_intent import (
    AnswerMode,
    AnswerPlan,
    fact_matches_metric_family,
    parse_question_intent,
)
from app.services.question_time_scope import ResearchTimeScope


@dataclass(frozen=True, slots=True)
class AmbiguousValue:
    normalized_value: str
    claim: str
    fact_ids: list[str] = field(default_factory=list)
    citation_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MetricAmbiguity:
    comparable_metric: str
    period: str
    values: list[AmbiguousValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AnswerContext:
    plan: AnswerPlan
    primary_facts: list[ExtractedFactRead] = field(default_factory=list)
    optional_context_facts: list[ExtractedFactRead] = field(default_factory=list)
    ambiguities: list[MetricAmbiguity] = field(default_factory=list)
    summary_text: str = ""
    display_notes: list[str] = field(default_factory=list)
    verification_conflicted_count: int = 0


class AnswerPipeline:
    """Build the single answer contract consumed by reports and followups."""

    def __init__(
        self,
        *,
        metric_normalizer: FactMetricNormalizer | None = None,
        value_normalizer: FactValueNormalizer | None = None,
    ) -> None:
        self.metric_normalizer = metric_normalizer or FactMetricNormalizer()
        self.value_normalizer = value_normalizer or FactValueNormalizer()

    def build_context(
        self,
        *,
        company_name: str,
        question: str,
        verified_facts: list[ExtractedFactRead],
        verifications: list[VerificationResultRead],
        time_scope: ResearchTimeScope | None = None,
        conflicted_facts: list[ExtractedFactRead] | None = None,
    ) -> AnswerContext:
        plan = parse_question_intent(question, time_scope=time_scope)
        ambiguities = self.build_ambiguities(
            facts=[*verified_facts, *(conflicted_facts or [])],
            verifications=verifications,
        )
        verification_conflicted_count = sum(
            1 for item in verifications if _status_value(item.status) == "conflicted"
        )
        fact_set = select_facts_for_answer(
            question=question,
            facts=verified_facts,
            plan=plan,
            time_scope=time_scope,
            verification_conflicted_count=verification_conflicted_count,
        )

        # 严格意图下 verified 为空时，回退使用与问题意图匹配的 conflicted 事实，
        # 并在提示中说明口径差异，避免用户看到「没有可靠事实」而 PDF 明明有数据。
        intent_matched_conflicted: list[ExtractedFactRead] = []
        if not fact_set.primary_facts and plan.strict_metrics and plan.metric_families:
            intent_matched_conflicted = [
                f for f in (conflicted_facts or [])
                if fact_matches_metric_family(f.metric_name, f.claim, plan.metric_families)
            ]
            if intent_matched_conflicted:
                conflicted_set = select_facts_for_answer(
                    question=question,
                    facts=intent_matched_conflicted,
                    plan=plan,
                    time_scope=time_scope,
                    verification_conflicted_count=verification_conflicted_count,
                )
                fact_set = AnswerFactSet(
                    primary_facts=conflicted_set.primary_facts,
                    context_facts=[],
                    verification_conflicted_count=verification_conflicted_count,
                    metric_ambiguity_count=len(ambiguities),
                    gap_notes=[
                        "以下数据来自不同来源片段，口径可能不完全一致，建议以年报合并报表原文为准。"
                    ],
                )

        optional_context = self._optional_context(fact_set, plan)
        summary = compose_report_answer(
            company_name=company_name,
            question=question,
            fact_set=AnswerFactSet(
                primary_facts=fact_set.primary_facts,
                context_facts=optional_context,
                verification_conflicted_count=verification_conflicted_count,
                metric_ambiguity_count=len(ambiguities),
                gap_notes=fact_set.gap_notes,
            ),
            plan=plan,
        )
        notes = list(fact_set.gap_notes)
        if ambiguities:
            notes.append("同一指标同一期间存在多个口径，报告按已核验主事实回答，并在附录列出口径冲突。")
        return AnswerContext(
            plan=plan,
            primary_facts=fact_set.primary_facts,
            optional_context_facts=optional_context,
            ambiguities=ambiguities,
            summary_text=summary,
            display_notes=notes,
            verification_conflicted_count=verification_conflicted_count,
        )

    def build_ambiguities(
        self,
        *,
        facts: list[ExtractedFactRead],
        verifications: list[VerificationResultRead],
    ) -> list[MetricAmbiguity]:
        conflicted_ids = {
            item.fact_id for item in verifications if _status_value(item.status) == "conflicted"
        }
        grouped: dict[tuple[str, str], list[ExtractedFactRead]] = defaultdict(list)
        for fact in facts:
            if not fact.metric_name or not fact.period or not fact.value:
                continue
            if conflicted_ids and fact.id not in conflicted_ids:
                continue
            key = (
                self.metric_normalizer.comparable_key(fact.metric_name),
                fact.period.strip().lower(),
            )
            grouped[key].append(fact)

        ambiguities: list[MetricAmbiguity] = []
        for (metric, period), items in grouped.items():
            by_value: dict[str, list[ExtractedFactRead]] = defaultdict(list)
            for fact in items:
                by_value[self.value_normalizer.comparable_key(fact.value)].append(fact)
            if len(by_value) <= 1:
                continue
            values = [
                AmbiguousValue(
                    normalized_value=value,
                    claim=value_facts[0].claim,
                    fact_ids=[fact.id for fact in value_facts],
                    citation_refs=[
                        f"{fact.source_id}:{fact.chunk_id}" for fact in value_facts
                    ],
                )
                for value, value_facts in sorted(by_value.items())
            ]
            ambiguities.append(
                MetricAmbiguity(
                    comparable_metric=metric,
                    period=period,
                    values=values,
                )
            )
        return ambiguities

    def _optional_context(
        self,
        fact_set: AnswerFactSet,
        plan: AnswerPlan,
    ) -> list[ExtractedFactRead]:
        if plan.answer_mode == AnswerMode.TREND or not plan.metric_families:
            return fact_set.context_facts
        return []


def _status_value(status: object) -> str:
    return str(getattr(status, "value", status))

