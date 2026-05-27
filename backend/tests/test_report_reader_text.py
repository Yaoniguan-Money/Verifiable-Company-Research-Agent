from __future__ import annotations

from app.services.report_reader_text import format_risk_analysis_for_report


def test_format_risk_analysis_strips_meta_and_splits_bullets() -> None:
    raw = """
    根据您提供的公开信息片段，以下是对某A股上市公司的分析。

    ### 一、研发投入
    - 2024年数据存在542亿与1800亿冲突，使用前需核对年报。

 请注意，多数事实标注为 INSUFFICIENT。

    该公司2022年研发投入约为202.8亿元（来源：上市公司2022年年报）。
    """
    bullets = format_risk_analysis_for_report(raw)
    assert bullets
    assert all("根据您" not in item for item in bullets)
    assert all("INSUFFICIENT" not in item for item in bullets)
    assert all("202.8亿元" not in item for item in bullets)
    assert any("冲突" in item or "核对" in item for item in bullets)


def test_format_risk_analysis_empty_input() -> None:
    assert format_risk_analysis_for_report("") == []
    assert format_risk_analysis_for_report("   ") == []


def test_format_risk_analysis_non_positive_limit_returns_empty() -> None:
    assert format_risk_analysis_for_report("一条足够长的风险观察内容", max_bullets=0) == []
    assert format_risk_analysis_for_report("一条足够长的风险观察内容", max_bullets=-1) == []
