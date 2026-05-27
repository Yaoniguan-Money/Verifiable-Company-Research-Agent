from __future__ import annotations

from app.services.fact_plausibility import (
    is_implausible_extracted_value,
    is_section_heading_line,
)


def test_section_heading_line_detects_chapter_title() -> None:
    assert is_section_heading_line("4、研发投入")
    assert not is_section_heading_line("研发费用 57,978,105,000.00 53,194,745,000.00")


def test_implausible_rd_money_values() -> None:
    assert is_implausible_extracted_value("R&D_expenditure", "4元")
    assert not is_implausible_extracted_value("R&D_expenditure", "542亿元")


def test_cumulative_rd_phrase_is_filtered() -> None:
    assert is_implausible_extracted_value(
        "R&D_expenditure",
        "1800亿元",
        context="累计研发投入超1,800亿元",
    )


def test_metric_unit_rules_reject_money_for_sales_volume() -> None:
    assert is_implausible_extracted_value("sales_volume", "100亿元")


def test_money_metric_rejects_percent_with_trailing_space() -> None:
    assert is_implausible_extracted_value("revenue", "12.3% \n")
