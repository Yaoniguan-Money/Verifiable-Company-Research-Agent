"""Tests for metric-name normalization used by verification."""

from __future__ import annotations

from app.services.fact_metric_normalization import FactMetricNormalizer


def test_rd_metric_aliases_share_one_key() -> None:
    normalizer = FactMetricNormalizer()

    expected = normalizer.comparable_key("R&D_expenditure")
    assert normalizer.comparable_key("r_and_d") == expected
    assert normalizer.comparable_key("research_expense") == expected
    assert normalizer.comparable_key("\u7814\u53d1\u8d39\u7528") == expected
    assert normalizer.comparable_key("\u7814\u53d1\u6295\u5165") == normalizer.comparable_key("R&D_total_spending")


def test_profit_metrics_keep_accounting_boundaries() -> None:
    normalizer = FactMetricNormalizer()

    assert normalizer.comparable_key("net_profit") != normalizer.comparable_key("net_profit_parent")
    assert normalizer.comparable_key("net_profit_parent") != normalizer.comparable_key(
        "net_profit_deducted"
    )
    assert normalizer.comparable_key("\u5f52\u6bcd\u51c0\u5229\u6da6") == "net_profit_parent"


def test_dimension_is_preserved_for_segment_metrics() -> None:
    normalizer = FactMetricNormalizer()

    assert normalizer.comparable_key("revenue_segment: \u836f\u54c1 ") == normalizer.comparable_key(
        "revenue_segment:\u836f\u54c1"
    )
    assert normalizer.comparable_key("revenue_segment:\u836f\u54c1") != normalizer.comparable_key(
        "revenue_segment:\u5065\u5eb7\u54c1"
    )
