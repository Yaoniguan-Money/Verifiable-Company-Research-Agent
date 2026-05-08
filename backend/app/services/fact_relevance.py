"""Question-aware fact relevance scoring for report assembly."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.fact import ExtractedFactRead


@dataclass(frozen=True, slots=True)
class FactRelevanceResult:
    core_facts: list[ExtractedFactRead] = field(default_factory=list)
    supporting_facts: list[ExtractedFactRead] = field(default_factory=list)
    intent_labels: list[str] = field(default_factory=list)


class FactRelevanceService:
    """Select facts that directly answer the research question.

    当前是可测试的规则层：先用问题意图约束事实展示顺序，避免报告首页被无关财务事实淹没。
    后续可替换为 embedding/LLM reranker，但输出契约应保持稳定。
    """

    def classify(
        self,
        *,
        question: str,
        facts: list[ExtractedFactRead],
    ) -> FactRelevanceResult:
        intents = self._detect_intents(question)
        if not facts:
            return FactRelevanceResult(intent_labels=sorted(intents))
        if not intents:
            return FactRelevanceResult(core_facts=facts, intent_labels=["general"])

        core: list[ExtractedFactRead] = []
        supporting: list[ExtractedFactRead] = []
        for fact in facts:
            score = self._score_fact(fact, intents)
            if score >= 2:
                core.append(fact)
            else:
                supporting.append(fact)

        return FactRelevanceResult(
            core_facts=core,
            supporting_facts=supporting,
            intent_labels=sorted(intents),
        )

    def _detect_intents(self, question: str) -> set[str]:
        q = question.lower()
        intents: set[str] = set()
        if any(token in q for token in ("研发", "r&d", "rd", "research")):
            intents.add("rd")
        if any(token in q for token in ("收入结构", "营收结构", "分业务", "业务结构", "收入构成")):
            intents.add("revenue_structure")
        elif any(token in q for token in ("收入", "营收", "营业收入", "revenue")):
            intents.add("revenue")
        if any(token in q for token in ("产能", "扩张", "产量", "销量", "capacity", "production")):
            intents.add("capacity")
        if any(token in q for token in ("净利润", "利润", "profit")):
            intents.add("profit")
        if any(token in q for token in ("风险", "不确定", "risk")):
            intents.add("risk")
        return intents

    def _score_fact(self, fact: ExtractedFactRead, intents: set[str]) -> int:
        metric = (fact.metric_name or "").lower()
        claim = fact.claim.lower()
        score = 0

        if "rd" in intents and (metric.startswith("r&d") or "研发" in claim):
            score += 3
        if "revenue_structure" in intents and (
            metric.startswith("revenue_segment") or "收入结构" in claim or "分业务" in claim
        ):
            score += 3
        if "revenue" in intents and (
            metric == "revenue" or metric.startswith("revenue_segment") or "收入" in claim
        ):
            score += 2
        if "capacity" in intents and (
            metric.startswith("production_capacity")
            or metric.startswith("production_volume")
            or metric.startswith("sales_volume")
            or any(token in claim for token in ("产能", "产量", "销量", "扩张"))
        ):
            score += 3
        if "profit" in intents and ("profit" in metric or "利润" in claim):
            score += 2
        if "risk" in intents and any(token in claim for token in ("风险", "不确定", "波动", "冲突")):
            score += 2

        return score
