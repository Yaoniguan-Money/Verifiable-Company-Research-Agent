"""从研究问题解析时间倾向：默认软约束（排序优先），仅在意图明确时硬过滤。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_CHINESE_YEAR_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass(frozen=True, slots=True)
class ResearchTimeScope:
    """用户问题中的时间倾向（不等于强制丢弃其他年份）。"""

    window_years: int | None = None
    """偏好最近 N 个完整披露年；None 表示未限定窗口。"""

    explicit_years: frozenset[int] | None = None
    """问题中点名的日历年份（如 2024 年）。"""

    strict: bool = False
    """为 True 时才会硬过滤来源/事实；否则只影响排序与检索提示。"""

    source: str = "rule"

    @property
    def lookback_years(self) -> int:
        if self.window_years is not None:
            return max(self.window_years + 1, 2)
        if self.explicit_years:
            current = datetime.now(timezone.utc).year
            span = current - min(self.explicit_years) + 1
            return max(2, min(span, 10))
        return 4

    def preferred_years(self, *, now: datetime | None = None) -> set[int]:
        if self.explicit_years:
            return set(self.explicit_years)
        if self.window_years is None:
            return set()
        current = (now or datetime.now(timezone.utc)).year
        latest_completed = current - 1
        return {
            latest_completed - offset
            for offset in range(self.window_years)
            if latest_completed - offset > 0
        }

    def cninfo_search_hint(self) -> str:
        if self.explicit_years:
            years = "、".join(str(y) for y in sorted(self.explicit_years))
            return f"用户关注 {years} 年的披露，优先对应期间年报/半年报。"
        if self.window_years == 1:
            return "用户更关注最近一个完整会计年度，优先最新年报或半年报，多年对比仅作辅助。"
        if self.window_years is not None:
            return (
                f"用户更关注最近约 {self.window_years} 个会计年度，"
                "优先对应期间披露，更早年份仅在有直接证据时简要提及。"
            )
        return "时间范围以研究问题为准，优先与问题期间直接相关的披露。"

    def suggested_source_limit(self, *, default_top_k: int) -> int:
        """建议下载份数：软约束时不砍太狠，避免误伤。"""
        if self.strict and self.window_years is not None:
            return min(default_top_k, max(self.window_years + 1, 1))
        if self.window_years is not None:
            return min(default_top_k, max(self.window_years + 2, 2))
        return default_top_k


def parse_research_time_scope(
    question: str,
    *,
    default_lookback_years: int = 4,
    now: datetime | None = None,
) -> ResearchTimeScope | None:
    """规则解析时间倾向；无法解析返回 None（由调用方保持默认检索行为）。"""
    normalized = (question or "").replace(" ", "")
    if not normalized:
        return None

    explicit_years = frozenset(int(m.group(0)) for m in re.finditer(r"20\d{2}", normalized))
    window: int | None = None

    digit_match = re.search(r"(?:近|最近)(\d{1,2})年", normalized)
    if digit_match:
        window = int(digit_match.group(1))

    if window is None:
        chinese_match = re.search(r"(?:近|最近)([一二两三四五六七八九十])年", normalized)
        if chinese_match:
            window = _CHINESE_YEAR_NUMBERS.get(chinese_match.group(1))

    if window is None and re.search(
        r"(?:近一年|过去一年|过去1年|最近一年|上年|去年|当期|本报告期|最新(?:一期|财报|年报))",
        normalized,
    ):
        window = 1

    if window is None and re.search(r"(?:今年|本年度|当年)", normalized):
        window = 1

    if window is None and not explicit_years:
        return None

    if window is not None:
        window = max(1, min(window, 10))

    strict = _detect_strict_time_intent(normalized, explicit_years=explicit_years, window=window)
    lookback_cap = default_lookback_years
    scope = ResearchTimeScope(
        window_years=window,
        explicit_years=explicit_years or None,
        strict=strict,
        source="rule",
    )
    _ = lookback_cap, now  # lookback 由属性动态计算；now 保留供测试注入扩展
    return scope


def resolve_research_time_scope(
    question: str,
    *,
    default_lookback_years: int = 4,
    llm_provider: LLMProvider | None = None,
    allow_llm: bool = True,
) -> ResearchTimeScope | None:
    """规则优先；规则未命中且允许时，用 LLM 轻量推断（失败则返回 None）。"""
    scope = parse_research_time_scope(question, default_lookback_years=default_lookback_years)
    if scope is not None:
        return scope
    if not allow_llm or llm_provider is None:
        return None
    return _parse_time_scope_llm(question, llm_provider)


def _detect_strict_time_intent(
    normalized: str,
    *,
    explicit_years: frozenset[int],
    window: int | None,
) -> bool:
    if re.search(r"(仅|只要|仅限|只看|专门|单独|不要其他年份)", normalized):
        return True
    if explicit_years and not re.search(r"(对比|比较|变化|趋势|逐年|历年|各年|多年)", normalized):
        return len(explicit_years) <= 2
    if window == 1 and re.search(r"(仅|只要|仅限|只看|不要.*(?:多年|历年))", normalized):
        return True
    return False


def _parse_time_scope_llm(question: str, llm_provider: LLMProvider) -> ResearchTimeScope | None:
    try:
        raw = llm_provider.infer_research_time_scope(question)
    except Exception:  # noqa: BLE001
        logger.debug("LLM 时间范围推断失败", exc_info=True)
        return None
    if not raw:
        return None
    return _scope_from_llm_payload(raw)


def _scope_from_llm_payload(payload: dict[str, Any]) -> ResearchTimeScope | None:
    window = payload.get("window_years")
    if window is not None:
        try:
            window = max(1, min(int(window), 10))
        except (TypeError, ValueError):
            window = None
    years_raw = payload.get("explicit_years") or []
    explicit: set[int] = set()
    if isinstance(years_raw, list):
        for item in years_raw:
            try:
                year = int(item)
            except (TypeError, ValueError):
                continue
            if 1990 <= year <= 2100:
                explicit.add(year)
    strict = bool(payload.get("strict"))
    if window is None and not explicit:
        return None
    return ResearchTimeScope(
        window_years=window,
        explicit_years=frozenset(explicit) or None,
        strict=strict,
        source="llm",
    )


def period_year(period: str | None) -> int | None:
    if not period:
        return None
    match = re.search(r"20\d{2}", period)
    return int(match.group(0)) if match else None


def fact_matches_time_scope(
    fact_period: str | None,
    scope: ResearchTimeScope | None,
    *,
    now: datetime | None = None,
) -> bool:
    """严格模式下用于硬过滤；软模式请用 fact_time_scope_rank_key。"""
    if scope is None or not scope.strict:
        return True
    preferred = scope.preferred_years(now=now)
    if not preferred:
        return True
    year = period_year(fact_period)
    if not year:
        return True
    return year in preferred


def fact_time_scope_rank_key(
    fact_period: str | None,
    scope: ResearchTimeScope | None,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """排序键：越靠前越符合用户时间倾向（0=在偏好年内）。"""
    year = period_year(fact_period) or 0
    if scope is None:
        return (1, -year)
    preferred = scope.preferred_years(now=now)
    if not preferred:
        return (1, -year)
    return (0 if year in preferred else 1, -year)


def parse_llm_time_scope_json(text: str) -> dict[str, Any] | None:
    """解析 LLM 返回的 JSON（容忍 markdown 代码块）。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
