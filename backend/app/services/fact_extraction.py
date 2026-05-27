"""结构化事实抽取服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import (
    SOURCE_CREDIBILITY_SCORE_METADATA_KEY,
    SOURCE_METADATA_KEY,
    blocks_high_confidence_fact,
)
from app.schemas.fact import (
    ExtractedFactCreate,
    ExtractedFactExtractionInput,
    ExtractedFactExtractionOutput,
)
from app.schemas.retrieval import RetrievedEvidence
from app.services.fact_patterns import (
    FACT_RULES,
    YEAR_PATTERN,
)
from app.services.fact_plausibility import is_implausible_extracted_value
from app.services.financial_table_extraction import (
    FinancialTableExtractionService,
    claim_label,
    metric_with_optional_dimension,
    value_and_unit,
)
from app.services.question_time_scope import parse_research_time_scope


@dataclass(frozen=True, slots=True)
class _ExtractionChunk:
    task_id: str
    source_id: str | None
    chunk_id: str | None
    text: str
    metadata: dict | None = None


class FactExtractionService:
    """规则抽取服务：将证据文本映射为结构化事实。"""

    def extract_from_chunks(
        self,
        *,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> ExtractedFactExtractionOutput:
        normalized = [
            _ExtractionChunk(
                task_id=ch.task_id,
                source_id=ch.source_id,
                chunk_id=ch.id,
                text=ch.text,
                metadata=ch.metadata,
            )
            for ch in chunks
        ]
        return self._extract(
            task_id=task_id,
            company_name=company_name,
            question=question,
            chunks=normalized,
        )

    def extract_from_retrieved_evidences(
        self,
        *,
        task_id: str,
        company_name: str,
        question: str,
        evidences: list[RetrievedEvidence],
    ) -> ExtractedFactExtractionOutput:
        normalized = [
            _ExtractionChunk(
                task_id=ev.task_id,
                source_id=ev.source_id,
                chunk_id=ev.chunk_id,
                text=ev.text,
                metadata=ev.metadata,
            )
            for ev in evidences
        ]
        return self._extract(
            task_id=task_id,
            company_name=company_name,
            question=question,
            chunks=normalized,
        )

    def _extract(
        self,
        *,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[_ExtractionChunk],
    ) -> ExtractedFactExtractionOutput:
        facts: list[ExtractedFactCreate] = []
        seen: set[tuple[str, str | None, str | None, str | None]] = set()
        known_period_keys: set[tuple[str | None, str | None, str | None]] = set()
        for ch in chunks:
            if ch.task_id != task_id:
                raise ValueError(
                    f"fact extraction 输入 task_id 不一致: expected={task_id}, actual={ch.task_id}"
                )
            if not ch.source_id or not ch.chunk_id:
                # 无法追溯则直接跳过，禁止伪造主键。
                continue
            if self._skip_high_confidence_extraction(ch.metadata):
                continue

            # 统一输入契约，避免后续替换 extractor 时输入漂移。
            ExtractedFactExtractionInput(
                task_id=task_id,
                source_id=ch.source_id,
                chunk_id=ch.chunk_id,
                chunk_text=ch.text,
                company_name=company_name,
                question=question,
            )

            for fact in self._extract_facts_from_text(
                task_id=task_id,
                source_id=ch.source_id,
                chunk_id=ch.chunk_id,
                text=ch.text,
                question=question,
            ):
                key = (fact.source_id, fact.metric_name, fact.period, fact.value)
                periodless_key = (fact.source_id, fact.metric_name, fact.value)
                if fact.period == "unknown_period" and periodless_key in known_period_keys:
                    continue
                if fact.period != "unknown_period":
                    facts = [
                        item
                        for item in facts
                        if not (
                            item.period == "unknown_period"
                            and (item.source_id, item.metric_name, item.value) == periodless_key
                        )
                    ]
                    known_period_keys.add(periodless_key)
                if key in seen:
                    continue
                facts.append(fact)
                seen.add(key)
        return ExtractedFactExtractionOutput(task_id=task_id, facts=facts)

    def _extract_facts_from_text(
        self,
        *,
        task_id: str,
        source_id: str,
        chunk_id: str,
        text: str,
        question: str = "",
    ) -> list[ExtractedFactCreate]:
        scope = parse_research_time_scope(question)
        allowed_years: set[int] | None = None
        if scope is not None and (scope.strict or scope.window_years == 1):
            preferred = scope.preferred_years()
            if preferred:
                allowed_years = preferred
        table_result = FinancialTableExtractionService().extract(
            task_id=task_id,
            source_id=source_id,
            chunk_id=chunk_id,
            text=text,
            allowed_years=allowed_years,
        )
        out = table_result.facts
        occupied_spans = table_result.handled_spans

        for rule in FACT_RULES:
            for m in re.finditer(rule.pattern, text):
                if self._overlaps(m.span(), occupied_spans):
                    continue
                occupied_spans.append(m.span())
                period = self._period_near_match(text=text, match_start=m.start())
                value, unit = self._value_and_unit(m)
                metric_name = self._metric_name_with_dimension(rule.metric_name, m)
                if self._should_skip_rule_value(
                    metric_name=metric_name,
                    value=value,
                    text=text,
                    match_start=m.start(),
                ):
                    continue
                metric_label = claim_label(rule.metric_name, metric_name)
                claim = (
                    f"{period}年{metric_label}为{value}"
                    if period != "unknown_period"
                    else f"期间未识别：{metric_label}为{value}"
                )
                out.append(
                    ExtractedFactCreate(
                        task_id=task_id,
                        claim=claim,
                        metric_name=metric_name,
                        value=value,
                        period=period,
                        source_id=source_id,
                        chunk_id=chunk_id,
                        confidence=0.76,
                    )
                )
        return out

    def _skip_high_confidence_extraction(self, metadata: dict | None) -> bool:
        if not metadata:
            return False
        source_metadata = metadata.get(SOURCE_METADATA_KEY) or {}
        return blocks_high_confidence_fact(
            source_metadata=source_metadata if isinstance(source_metadata, dict) else None,
            credibility_score=metadata.get(SOURCE_CREDIBILITY_SCORE_METADATA_KEY),
        )

    def _metric_name_with_dimension(self, metric_name: str, match: re.Match[str]) -> str:
        groups = match.groupdict()
        dimension = groups.get("segment") or groups.get("product")
        return metric_with_optional_dimension(metric_name, dimension)

    def _overlaps(self, span: tuple[int, int], occupied_spans: list[tuple[int, int]]) -> bool:
        start, end = span
        return any(start < taken_end and end > taken_start for taken_start, taken_end in occupied_spans)

    def _value_and_unit(self, match: re.Match[str]) -> tuple[str, str]:
        # 部分规则会在同一表达式中出现两组命名捕获；取实际命中的那一组。
        return value_and_unit(match)

    def _should_skip_rule_value(
        self,
        *,
        metric_name: str,
        value: str,
        text: str,
        match_start: int,
    ) -> bool:
        if value.endswith("%"):
            metric_base = metric_name.split(":", 1)[0]
            if metric_base in {
                "R&D_expenditure",
                "R&D_total_spending",
                "revenue",
                "revenue_segment",
                "net_profit",
                "net_profit_parent",
                "net_profit_deducted",
            }:
                return True
        context_start = max(0, match_start - 40)
        context_end = min(len(text), match_start + 80)
        if is_implausible_extracted_value(
            metric_name,
            value,
            context=text[context_start:context_end],
        ):
            return True
        return False

    def _period_near_match(self, *, text: str, match_start: int) -> str:
        # 高密度资料常在同一段同时出现多个年份，优先取指标前最近的年份，避免制造假冲突。
        prefix = text[max(0, match_start - 160) : match_start]
        prefix_years = list(re.finditer(YEAR_PATTERN, prefix))
        if prefix_years:
            return prefix_years[-1].group("year")

        suffix = text[match_start : match_start + 48]
        suffix_year = re.search(YEAR_PATTERN, suffix)
        return suffix_year.group("year") if suffix_year else "unknown_period"

