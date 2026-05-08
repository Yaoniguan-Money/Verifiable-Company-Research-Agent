from __future__ import annotations

from app.evaluation import score_public_regression_case, score_public_regression_suite


def test_public_regression_case_score_quantifies_coverage() -> None:
    score = score_public_regression_case(
        company_name="Sample Public Co",
        expected_metric_groups=["R&D_expenditure", "revenue", "production_capacity"],
        observed_metric_groups=["R&D_expenditure", "revenue", "net_profit_parent"],
        source_count=2,
        fact_count=12,
        minimum_coverage_ratio=0.6,
    )

    assert score.metric_coverage_ratio == 0.6667
    assert score.evidence_density == 6.0
    assert score.matched_metric_groups == ["R&D_expenditure", "revenue"]
    assert score.missing_metric_groups == ["production_capacity"]
    assert score.unexpected_metric_groups == ["net_profit_parent"]
    assert score.passed


def test_public_regression_suite_score_summarizes_cases() -> None:
    a = score_public_regression_case(
        company_name="A",
        expected_metric_groups=["R&D_expenditure"],
        observed_metric_groups=["R&D_expenditure"],
        source_count=1,
        fact_count=2,
    )
    b = score_public_regression_case(
        company_name="B",
        expected_metric_groups=["R&D_expenditure", "revenue"],
        observed_metric_groups=["revenue"],
        source_count=1,
        fact_count=2,
    )

    suite = score_public_regression_suite([a, b])

    assert suite.case_count == 2
    assert suite.passed_count == 1
    assert suite.average_metric_coverage_ratio == 0.75
    assert not suite.passed
    assert suite.to_dict()["passed"] is False


def test_public_regression_suite_score_renders_markdown_summary() -> None:
    passed = score_public_regression_case(
        company_name="公司A",
        expected_metric_groups=["revenue"],
        observed_metric_groups=["revenue"],
        source_count=2,
        fact_count=10,
    )
    failed = score_public_regression_case(
        company_name="公司B",
        expected_metric_groups=["R&D_expenditure", "revenue"],
        observed_metric_groups=["revenue", "net_profit_parent"],
        source_count=1,
        fact_count=3,
        minimum_coverage_ratio=0.7,
    )

    markdown = score_public_regression_suite([passed, failed]).to_markdown()

    assert (
        "| case_count | passed_count | average_metric_coverage_ratio | "
        "total_source_count | total_fact_count |"
    ) in markdown
    assert "| 2 | 1 | 0.7500 | 3 | 13 |" in markdown
    assert (
        "| company_name | source_count | fact_count | metric_coverage_ratio | "
        "missing_metric_groups | unexpected_metric_groups | passed |"
    ) in markdown
    assert "| 公司A | 2 | 10 | 1.0000 | - | - | true |" in markdown
    assert "| 公司B | 1 | 3 | 0.5000 | R&D_expenditure | net_profit_parent | false |" in markdown
