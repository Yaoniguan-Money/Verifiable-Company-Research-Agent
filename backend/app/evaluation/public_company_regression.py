"""Quantitative scoring for public-company regression cases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PublicRegressionCaseScore:
    company_name: str
    source_count: int
    fact_count: int
    expected_metric_groups: list[str]
    observed_metric_groups: list[str]
    matched_metric_groups: list[str]
    missing_metric_groups: list[str]
    unexpected_metric_groups: list[str]
    metric_coverage_ratio: float
    evidence_density: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublicRegressionSuiteScore:
    case_count: int
    passed_count: int
    average_metric_coverage_ratio: float
    total_source_count: int
    total_fact_count: int
    cases: list[PublicRegressionCaseScore]

    @property
    def passed(self) -> bool:
        return self.case_count > 0 and self.passed_count == self.case_count

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["passed"] = self.passed
        return data

    def to_markdown(self) -> str:
        return render_public_regression_suite_markdown(self)


def score_public_regression_case(
    *,
    company_name: str,
    expected_metric_groups: list[str],
    observed_metric_groups: list[str],
    source_count: int,
    fact_count: int,
    minimum_coverage_ratio: float = 0.7,
) -> PublicRegressionCaseScore:
    expected = sorted({_normalize_group(item) for item in expected_metric_groups if item})
    observed = sorted({_normalize_group(item) for item in observed_metric_groups if item})
    expected_set = set(expected)
    observed_set = set(observed)
    matched = sorted(expected_set & observed_set)
    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)
    coverage = round(len(matched) / len(expected), 4) if expected else 1.0
    density = round(fact_count / source_count, 4) if source_count > 0 else 0.0
    return PublicRegressionCaseScore(
        company_name=company_name,
        source_count=source_count,
        fact_count=fact_count,
        expected_metric_groups=expected,
        observed_metric_groups=observed,
        matched_metric_groups=matched,
        missing_metric_groups=missing,
        unexpected_metric_groups=unexpected,
        metric_coverage_ratio=coverage,
        evidence_density=density,
        passed=source_count > 0 and fact_count > 0 and coverage >= minimum_coverage_ratio,
    )


def score_public_regression_suite(
    case_scores: list[PublicRegressionCaseScore],
) -> PublicRegressionSuiteScore:
    case_count = len(case_scores)
    passed_count = sum(1 for item in case_scores if item.passed)
    total_sources = sum(item.source_count for item in case_scores)
    total_facts = sum(item.fact_count for item in case_scores)
    average_coverage = (
        round(sum(item.metric_coverage_ratio for item in case_scores) / case_count, 4)
        if case_count
        else 0.0
    )
    return PublicRegressionSuiteScore(
        case_count=case_count,
        passed_count=passed_count,
        average_metric_coverage_ratio=average_coverage,
        total_source_count=total_sources,
        total_fact_count=total_facts,
        cases=case_scores,
    )


def render_public_regression_suite_markdown(score: PublicRegressionSuiteScore) -> str:
    lines = [
        "## 公开资料回归评测结果",
        "",
        "### 总览",
        "",
        "| case_count | passed_count | average_metric_coverage_ratio | total_source_count | total_fact_count |",
        "|---:|---:|---:|---:|---:|",
        "| "
        f"{score.case_count} | "
        f"{score.passed_count} | "
        f"{score.average_metric_coverage_ratio:.4f} | "
        f"{score.total_source_count} | "
        f"{score.total_fact_count} |",
        "",
        "### 分公司结果",
        "",
        (
            "| company_name | source_count | fact_count | metric_coverage_ratio | "
            "missing_metric_groups | unexpected_metric_groups | passed |"
        ),
        "|---|---:|---:|---:|---|---|---|",
    ]
    for case in score.cases:
        missing = ", ".join(case.missing_metric_groups) if case.missing_metric_groups else "-"
        unexpected = ", ".join(case.unexpected_metric_groups) if case.unexpected_metric_groups else "-"
        lines.append(
            "| "
            f"{_escape_markdown_cell(case.company_name)} | "
            f"{case.source_count} | "
            f"{case.fact_count} | "
            f"{case.metric_coverage_ratio:.4f} | "
            f"{_escape_markdown_cell(missing)} | "
            f"{_escape_markdown_cell(unexpected)} | "
            f"{str(case.passed).lower()} |"
        )
    return "\n".join(lines)


def _normalize_group(metric_group: str) -> str:
    return metric_group.strip().split(":", 1)[0]


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
