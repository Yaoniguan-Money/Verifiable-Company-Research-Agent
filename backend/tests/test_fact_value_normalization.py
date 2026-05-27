"""Tests for comparable fact-value normalization."""

from __future__ import annotations

from app.services.fact_value_normalization import FactValueNormalizer


def test_money_units_normalize_to_same_comparable_key() -> None:
    normalizer = FactValueNormalizer()

    assert normalizer.comparable_key("100\u4ebf\u5143") == normalizer.comparable_key(
        "1000000\u4e07\u5143"
    )
    assert normalizer.comparable_key("100\u4ebf\u5143") == normalizer.comparable_key(
        "10000000000\u5143"
    )


def test_count_units_normalize_to_base_unit() -> None:
    normalizer = FactValueNormalizer()

    assert normalizer.comparable_key("4,479,392\u8f86") == normalizer.comparable_key(
        "447.9392\u4e07\u8f86"
    )
    assert normalizer.comparable_key("12\u4e07\u5428") == normalizer.comparable_key(
        "120000\u5428"
    )


def test_energy_units_normalize_to_mwh() -> None:
    normalizer = FactValueNormalizer()

    assert normalizer.comparable_key("1GWh") == normalizer.comparable_key("1000MWh")


def test_unparsed_values_fall_back_to_clean_raw_string() -> None:
    normalizer = FactValueNormalizer()

    assert normalizer.comparable_key(" abc, 123 ") == "abc123"
