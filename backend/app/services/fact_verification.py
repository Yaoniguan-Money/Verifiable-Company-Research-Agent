"""Deterministic fact verification for extracted public-company facts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import get_settings
from app.schemas.common import (
    SourceAuthority,
    SourceLayer,
    authority_label,
    is_official_body_layer,
    source_layer_from_metadata,
)
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.verification import VerificationOutput, VerificationResultCreate
from app.services.fact_metric_normalization import FactMetricNormalizer
from app.services.fact_plausibility import is_implausible_extracted_value
from app.services.fact_value_normalization import FactValueNormalizer


@dataclass(frozen=True, slots=True)
class _FactItem:
    id: str
    task_id: str
    metric_name: str | None
    period: str | None
    value: str | None
    source_id: str
    source_published_at: datetime | None = None
    source_credibility: float | None = None
    source_metadata: dict | None = None
    confidence: float = 0.0


class FactVerificationService:
    """Verify extracted facts with traceable rule-based decisions."""

    def __init__(
        self,
        value_normalizer: FactValueNormalizer | None = None,
        metric_normalizer: FactMetricNormalizer | None = None,
    ) -> None:
        self.value_normalizer = value_normalizer or FactValueNormalizer()
        self.metric_normalizer = metric_normalizer or FactMetricNormalizer()

    def verify_facts(
        self,
        *,
        task_id: str,
        facts: list[ExtractedFactRead],
        source_context: dict[str, tuple[datetime | None, float | None] | tuple[datetime | None, float | None, dict | None]] | None = None,
    ) -> VerificationOutput:
        items = [
            _FactItem(
                id=f.id,
                task_id=f.task_id,
                metric_name=f.metric_name,
                period=f.period,
                value=f.value,
                source_id=f.source_id,
                source_published_at=self._source_context_value(source_context, f.source_id)[0],
                source_credibility=self._source_context_value(source_context, f.source_id)[1],
                source_metadata=self._source_context_value(source_context, f.source_id)[2],
                confidence=float(f.confidence or 0),
            )
            for f in facts
            if f.task_id == task_id
        ]
        return self._verify(task_id=task_id, items=items)

    def verify_fact_creates(
        self,
        *,
        task_id: str,
        facts: list[ExtractedFactCreate],
        id_prefix: str = "tmp_fact_",
        source_context: dict[str, tuple[datetime | None, float | None] | tuple[datetime | None, float | None, dict | None]] | None = None,
    ) -> VerificationOutput:
        items = [
            _FactItem(
                id=f"{id_prefix}{idx}",
                task_id=f.task_id,
                metric_name=f.metric_name,
                period=f.period,
                value=f.value,
                source_id=f.source_id,
                source_published_at=self._source_context_value(source_context, f.source_id)[0],
                source_credibility=self._source_context_value(source_context, f.source_id)[1],
                source_metadata=self._source_context_value(source_context, f.source_id)[2],
                confidence=float(f.confidence or 0),
            )
            for idx, f in enumerate(facts)
            if f.task_id == task_id
        ]
        return self._verify(task_id=task_id, items=items)

    _LLM_CONFIDENCE = 1.0

    def _verify(self, *, task_id: str, items: list[_FactItem]) -> VerificationOutput:
        now = datetime.now(timezone.utc)
        fresh_year_threshold = now.year - 5

        # Separate LLM facts (confidence >= 1.0) from regex facts.
        # LLM facts skip cross-source verification because the LLM
        # already read the full context to produce the value.
        llm_items: list[_FactItem] = []
        regex_items: list[_FactItem] = []
        for item in items:
            if item.confidence >= self._LLM_CONFIDENCE:
                llm_items.append(item)
            else:
                regex_items.append(item)

        results: list[VerificationResultCreate] = []

        # --- LLM facts: direct verify, only conflict with other LLM facts ---
        results.extend(self._verify_llm_facts(task_id, llm_items))

        # --- Regex facts: existing cross-source verification (unchanged) ---
        results.extend(self._verify_regex_facts(task_id, regex_items, fresh_year_threshold))

        return VerificationOutput(task_id=task_id, results=results)

    def _verify_llm_facts(
        self, task_id: str, items: list[_FactItem]
    ) -> list[VerificationResultCreate]:
        """LLM facts are trusted directly. Multiple LLM facts that disagree → conflicted."""
        results: list[VerificationResultCreate] = []

        # Basic validation only (missing fields, implausible values)
        valid_items: list[_FactItem] = []
        for item in items:
            rejection = self._rejection_detail(item)
            if rejection is not None:
                results.append(VerificationResultCreate(
                    fact_id=item.id, task_id=task_id,
                    status="rejected", confidence=0.2,
                    supporting_sources=[item.source_id] if item.source_id else [],
                    conflicting_sources=[],
                    reason=rejection[1], reason_code=rejection[0],
                ))
                continue
            valid_items.append(item)

        # Group by normalized metric + period
        groups: dict[tuple[str, str], list[_FactItem]] = defaultdict(list)
        for item in valid_items:
            if not item.metric_name or not item.period:
                groups[(f"__llm_missing__:{item.id}", "__missing__")].append(item)
                continue
            metric_key = self.metric_normalizer.comparable_key(item.metric_name)
            groups[(metric_key, item.period.strip().lower())].append(item)

        for group_items in groups.values():
            value_to_sources: dict[str, set[str]] = defaultdict(set)
            for item in group_items:
                value_to_sources[self.value_normalizer.comparable_key(item.value)].add(item.source_id)

            llm_value_conflict = len(value_to_sources) > 1

            if llm_value_conflict:
                # Multiple LLM facts disagree → real conflict
                all_sources = {item.source_id for item in group_items}
                for item in group_items:
                    results.append(VerificationResultCreate(
                        fact_id=item.id, task_id=task_id,
                        status="conflicted", confidence=0.50,
                        supporting_sources=[item.source_id],
                        conflicting_sources=sorted(all_sources - {item.source_id}),
                        reason="LLM 从不同片段中抽取出不同值，需人工核对口径",
                        reason_code="llm_value_conflict",
                    ))
            else:
                # Single LLM value or all LLM agree → verified
                supporting = sorted({item.source_id for item in group_items})
                for item in group_items:
                    results.append(VerificationResultCreate(
                        fact_id=item.id, task_id=task_id,
                        status="verified", confidence=0.92,
                        supporting_sources=supporting,
                        conflicting_sources=[],
                        reason="LLM 从完整上下文中抽取，已按语义校验采信",
                        reason_code="llm_extracted",
                    ))

        return results

    def _verify_regex_facts(
        self, task_id: str, items: list[_FactItem], fresh_year_threshold: int
    ) -> list[VerificationResultCreate]:
        """Existing cross-source verification for regex-extracted facts (unchanged)."""
        rejected_items: list[_FactItem] = []
        outdated_items: list[_FactItem] = []
        normal_items: list[_FactItem] = []

        for item in items:
            if self._rejection_detail(item) is not None:
                rejected_items.append(item)
                continue
            if self._is_outdated(item, fresh_year_threshold):
                outdated_items.append(item)
                continue
            normal_items.append(item)

        results: list[VerificationResultCreate] = []
        for item in rejected_items:
            reason_code, reason = self._rejection_detail(item) or (
                "invalid_fact_record", "事实记录不满足最小有效性要求，已拒绝",
            )
            results.append(VerificationResultCreate(
                fact_id=item.id, task_id=task_id,
                status="rejected", confidence=0.2,
                supporting_sources=[item.source_id] if item.source_id else [],
                conflicting_sources=[],
                reason=reason, reason_code=reason_code,
            ))

        for item in outdated_items:
            results.append(VerificationResultCreate(
                fact_id=item.id, task_id=task_id,
                status="outdated", confidence=0.5,
                supporting_sources=[item.source_id] if item.source_id else [],
                conflicting_sources=[],
                reason="来源时间或事实期间过旧，需补充更新资料",
                reason_code="outdated_period_or_source",
            ))

        groups: dict[tuple[str, str], list[_FactItem]] = defaultdict(list)
        for item in normal_items:
            if not item.metric_name or not item.period:
                groups[(f"__missing__:{item.id}", "__missing__")].append(item)
                continue
            metric_key = self.metric_normalizer.comparable_key(item.metric_name)
            groups[(metric_key, item.period.strip().lower())].append(item)

        for group_items in groups.values():
            source_set = {item.source_id for item in group_items}
            metric_keys = {
                self.metric_normalizer.comparable_key(item.metric_name) for item in group_items
            }
            raw_metric_keys = {
                (item.metric_name or "").strip().replace(" ", "_").lower()
                for item in group_items
            }
            value_to_sources: dict[str, set[str]] = defaultdict(set)
            raw_value_keys: set[str] = set()

            for item in group_items:
                value_to_sources[self.value_normalizer.comparable_key(item.value)].add(item.source_id)
                raw_value_keys.add((item.value or "").replace(" ", "").replace(",", "").strip().lower())

            multiple_sources = len(source_set) >= 2
            value_conflicted = len(value_to_sources) > 1
            metric_alias_used = len(metric_keys) == 1 and len(raw_metric_keys) > 1
            unit_normalized = len(value_to_sources) == 1 and len(raw_value_keys) > 1
            verification_block = self._verification_block_detail(group_items)

            truly_conflicted = value_conflicted and not unit_normalized

            if multiple_sources and truly_conflicted:
                for item in group_items:
                    results.append(VerificationResultCreate(
                        fact_id=item.id, task_id=task_id,
                        status="conflicted", confidence=0.42,
                        supporting_sources=[item.source_id],
                        conflicting_sources=sorted(source_set - {item.source_id}),
                        reason="同一指标同一期间在不同来源中出现不同取值",
                        reason_code="different_value_multi_source",
                    ))
            elif (
                truly_conflicted
                and get_settings().verification_treat_single_source_value_conflict
            ):
                for item in group_items:
                    results.append(
                        VerificationResultCreate(
                            fact_id=item.id,
                            task_id=task_id,
                            status="conflicted",
                            confidence=0.4,
                            supporting_sources=[item.source_id],
                            conflicting_sources=sorted(source_set) or [item.source_id],
                            reason="同一来源中同一指标同一期间出现多个不同取值，需要回到原文核对口径。",
                            reason_code="same_period_value_divergence",
                        )
                    )
            elif verification_block is None and not any(
                self._extract_numeric(item.value) is not None for item in group_items
            ):
                for item in group_items:
                    results.append(
                        VerificationResultCreate(
                            fact_id=item.id,
                            task_id=task_id,
                            status="insufficient",
                            confidence=0.52,
                            supporting_sources=[item.source_id],
                            conflicting_sources=[],
                            reason="事实取值不是可核对的数字或结构化口径，不能直接作为已验证指标。",
                            reason_code="non_numeric_value_not_verified",
                        )
                    )
            elif multiple_sources and verification_block is None:
                reason_code, reason = self._verified_reason(
                    metric_alias_used=metric_alias_used,
                    unit_normalized=unit_normalized,
                )
                supporting = sorted(source_set)
                for item in group_items:
                    results.append(
                        VerificationResultCreate(
                            fact_id=item.id,
                            task_id=task_id,
                            status="verified",
                            confidence=0.88,
                            supporting_sources=supporting,
                            conflicting_sources=[],
                            reason=reason,
                            reason_code=reason_code,
                        )
                    )
            elif verification_block is None and self._single_official_disclosure_trusted(
                group_items
            ):
                supporting = sorted(source_set)
                for item in group_items:
                    results.append(
                        VerificationResultCreate(
                            fact_id=item.id,
                            task_id=task_id,
                            status="verified",
                            confidence=0.82,
                            supporting_sources=supporting,
                            conflicting_sources=[],
                            reason="指标来自巨潮/交易所披露的正式年报或公告正文，已按单来源采信",
                            reason_code="official_disclosure_single_source",
                        )
                    )
            else:
                reason_code, reason = verification_block or (
                    "single_source_only",
                    "缺少可交叉验证的独立来源，当前证据不足",
                )
                for item in group_items:
                    results.append(
                        VerificationResultCreate(
                            fact_id=item.id,
                            task_id=task_id,
                            status="insufficient",
                            confidence=0.55,
                            supporting_sources=[item.source_id],
                            conflicting_sources=[],
                            reason=reason,
                            reason_code=reason_code,
                        )
                    )

        return results

    def _rejected_reason(self, item: _FactItem) -> str | None:
        detail = self._rejection_detail(item)
        return detail[1] if detail is not None else None

    def _rejection_detail(self, item: _FactItem) -> tuple[str, str] | None:
        if not item.source_id:
            return "missing_source_id", "缺少 source_id，无法建立最小可追溯性"
        if not item.metric_name or not item.period or not item.value:
            return "missing_required_fields", "缺少关键字段（metric_name/period/value）"
        numeric = self._extract_numeric(item.value)
        if numeric is not None and numeric <= 0:
            return "invalid_numeric_value", "数值异常（<=0），判定为无效事实"
        if is_implausible_extracted_value(item.metric_name or "", item.value or ""):
            return "invalid_numeric_value", "金额量级与指标类型不匹配，判定为无效事实"
        if item.source_credibility is not None and item.source_credibility < 0.2:
            return "low_credibility_source", "来源可信度过低，拒绝纳入验证结论"
        return None

    def _single_official_disclosure_trusted(self, items: list[_FactItem]) -> bool:
        """年报/公告正文单来源即可采信，不必强行要求第二来源交叉。"""
        if not items:
            return False
        for item in items:
            layer = source_layer_from_metadata(item.source_metadata)
            if not is_official_body_layer(layer):
                return False
            if item.source_credibility is not None and item.source_credibility < 0.5:
                return False
        return True

    def _verification_block_detail(self, items: list[_FactItem]) -> tuple[str, str] | None:
        if any(authority_label(item.source_credibility) == SourceAuthority.LOW for item in items):
            return "low_authority_source_not_verified", "事实包含低可信来源，不能直接进入 verified"
        layers = {source_layer_from_metadata(item.source_metadata) for item in items}
        if layers and layers <= {SourceLayer.OFFICIAL_ENTRY_PAGE}:
            return (
                "official_entry_page_only",
                "官方入口存在，但未抓取到具体披露正文，不能形成高置信验证结论",
            )
        return None

    def _source_context_value(
        self,
        source_context: dict[str, tuple[datetime | None, float | None] | tuple[datetime | None, float | None, dict | None]] | None,
        source_id: str,
    ) -> tuple[datetime | None, float | None, dict | None]:
        value = (source_context or {}).get(source_id)
        if value is None:
            return None, None, None
        if len(value) == 2:
            return value[0], value[1], None
        return value[0], value[1], value[2]

    def _is_outdated(self, item: _FactItem, threshold_year: int) -> bool:
        if item.source_published_at is not None and item.source_published_at.year < threshold_year:
            return True
        year = self._extract_year(item.period)
        return year is not None and year < threshold_year

    def _verified_reason(self, *, metric_alias_used: bool, unit_normalized: bool) -> tuple[str, str]:
        if metric_alias_used and unit_normalized:
            return (
                "metric_and_unit_normalized_match",
                "同一指标同一期间存在多个独立来源；指标别名与单位归一化后取值一致",
            )
        if metric_alias_used:
            return (
                "metric_alias_normalized_match",
                "同一指标同一期间存在多个独立来源；指标别名归一化后取值一致",
            )
        if unit_normalized:
            return (
                "unit_normalized_match",
                "同一指标同一期间存在多个独立来源；单位归一化后取值一致",
            )
        return (
            "same_value_multi_source",
            "同一指标同一期间存在多个独立来源且取值一致",
        )

    def _extract_year(self, period: str | None) -> int | None:
        if not period:
            return None
        digits = "".join(ch for ch in period if ch.isdigit())
        if len(digits) >= 4:
            try:
                return int(digits[:4])
            except ValueError:
                return None
        return None

    def _extract_numeric(self, value: str | None) -> float | None:
        if not value:
            return None
        chars = []
        has_dot = False
        for ch in value:
            if ch.isdigit():
                chars.append(ch)
            elif ch == "." and not has_dot:
                chars.append(ch)
                has_dot = True
        raw = "".join(chars).strip(".")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
