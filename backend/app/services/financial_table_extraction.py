from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.fact import ExtractedFactCreate
from app.services.fact_patterns import INLINE_VALUE_UNIT_PATTERN, METRIC_LABELS, YEAR_PATTERN


@dataclass(frozen=True, slots=True)
class TableExtractionResult:
    facts: list[ExtractedFactCreate]
    handled_spans: list[tuple[int, int]]


class FinancialTableExtractionService:
    """从 PDF 文本化表格中抽取关键财报字段。

    这里处理“表头年份 + 后续指标行”的稳定结构；普通自然语言仍交给 FactExtractionService。
    """

    def extract(
        self,
        *,
        task_id: str,
        source_id: str,
        chunk_id: str,
        text: str,
    ) -> TableExtractionResult:
        facts: list[ExtractedFactCreate] = []
        handled_spans: list[tuple[int, int]] = []
        current_years: list[str] = []
        current_unit: str | None = None
        has_wide_header = False
        offset = 0
        for line in text.splitlines(keepends=True):
            clean = line.strip()
            line_start = offset
            line_end = offset + len(line)
            offset = line_end

            years = [m.group("year") for m in re.finditer(YEAR_PATTERN, clean)]
            unit = self._unit_from_line(clean)
            if unit:
                current_unit = unit
            if all(mark in clean for mark in ("产能状况", "快报产量", "快报销量")):
                has_wide_header = True
            row_metric = self._table_row_metric(clean)
            wide_facts = self._extract_vehicle_wide_row(
                task_id=task_id,
                source_id=source_id,
                chunk_id=chunk_id,
                line=clean,
                years=current_years,
                has_wide_header=has_wide_header,
            )
            if wide_facts:
                facts.extend(wide_facts)
                handled_spans.append((line_start, line_end))
                continue
            values = extract_numeric_values(clean, fallback_unit=current_unit) if row_metric is not None else []
            if len(years) >= 2 and row_metric is None:
                current_years = years
            elif len(years) == 1 and not values and not current_years:
                current_years = years

            if row_metric is None or not current_years or not self._looks_like_table_row(clean):
                continue
            if not values:
                continue

            metric_base, dimension = row_metric
            for idx, value_match in enumerate(values[: len(current_years)]):
                value = value_match.value
                period = current_years[idx]
                metric_name = metric_with_optional_dimension(metric_base, dimension)
                label = claim_label(metric_base, metric_name)
                facts.append(
                    ExtractedFactCreate(
                        task_id=task_id,
                        claim=f"{period}年{label}为{value}",
                        metric_name=metric_name,
                        value=value,
                        period=period,
                        source_id=source_id,
                        chunk_id=chunk_id,
                        confidence=0.78,
                    )
                )
            handled_spans.append((line_start, line_end))

        return TableExtractionResult(facts=facts, handled_spans=handled_spans)

    def _extract_vehicle_wide_row(
        self,
        *,
        task_id: str,
        source_id: str,
        chunk_id: str,
        line: str,
        years: list[str],
        has_wide_header: bool = False,
    ) -> list[ExtractedFactCreate]:
        if not years or not (has_wide_header or any(mark in line for mark in ("产能状况", "快报产量", "快报销量", "销售收入"))):
            return []
        if len(years) > 1:
            # 宽表行通常承接上方单一年份表头；多年份行交给普通表格逻辑。
            return []
        product = self._vehicle_product_from_line(line)
        if product is None:
            return []
        values = [item.value for item in extract_numeric_values(line, fallback_unit=None)]
        # 宽表常见顺序：产能、产量、销量、销售收入。
        if len(values) < 3:
            return []
        year = years[0]
        specs = [
            ("production_capacity", values[0]),
            ("production_volume", values[1]),
            ("sales_volume", values[2]),
        ]
        if len(values) >= 4:
            specs.append(("revenue_segment", values[3]))
        facts: list[ExtractedFactCreate] = []
        for metric_base, value in specs:
            metric_name = metric_with_optional_dimension(metric_base, product)
            facts.append(
                ExtractedFactCreate(
                    task_id=task_id,
                    claim=f"{year}年{claim_label(metric_base, metric_name)}为{value}",
                    metric_name=metric_name,
                    value=value,
                    period=year,
                    source_id=source_id,
                    chunk_id=chunk_id,
                    confidence=0.74,
                )
            )
        return facts

    def _vehicle_product_from_line(self, line: str) -> str | None:
        candidates = ("乘用车", "商用车", "客车", "SUV", "MPV", "其他")
        for item in candidates:
            if item in line:
                return item
        return None

    def _unit_from_line(self, line: str) -> str | None:
        match = re.search(r"单位[:：]\s*(亿元|亿|千元|万元|元|%|辆|台|万辆|万台|吨|万吨|GWh|MWh)", line)
        if not match:
            return None
        unit = match.group(1)
        return "亿元" if unit == "亿" else unit

    def _looks_like_table_row(self, line: str) -> bool:
        if any(mark in line for mark in ("。", "；", ";")):
            return False
        return len(line) <= 220

    def _table_row_metric(self, line: str) -> tuple[str, str | None] | None:
        if not line:
            return None
        if "研发费用" in line or "研发投入" in line:
            return "R&D_expenditure", None
        if "营业收入" in line and "合计" in line:
            return "revenue", None
        if "收入" in line or "销售收入" in line:
            segment = self._dimension_before_value(line)
            if segment and segment not in {"收入", "销售收入", "营业收入", "主营业务收入"}:
                return "revenue_segment", segment
        if "产能状况" in line or "产能" in line:
            return "production_capacity", self._dimension_before_keyword(line, ("产能状况", "产能"))
        if "快报产量" in line or "产量" in line:
            return "production_volume", self._dimension_before_keyword(line, ("快报产量", "产量"))
        if "快报销量" in line or "销量" in line:
            return "sales_volume", self._dimension_before_keyword(line, ("快报销量", "销量"))
        return None

    def _dimension_before_value(self, line: str) -> str | None:
        value_match = re.search(INLINE_VALUE_UNIT_PATTERN, line)
        if value_match is None:
            value_match = re.search(
                r"(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?![A-Za-z0-9])",
                line,
            )
        prefix = line[: value_match.start()] if value_match else line
        prefix = re.sub(YEAR_PATTERN, "", prefix)
        prefix = re.sub(r"单位[:：]?.*$", "", prefix)
        prefix = prefix.replace("销售收入", "").replace("收入", "")
        return clean_dimension(prefix)

    def _dimension_before_keyword(self, line: str, keywords: tuple[str, ...]) -> str | None:
        positions = [line.find(keyword) for keyword in keywords if keyword in line]
        prefix = line[: min(positions)] if positions else line
        prefix = re.sub(YEAR_PATTERN, "", prefix)
        return clean_dimension(prefix)


def value_and_unit(match: re.Match[str]) -> tuple[str, str]:
    groups = match.groupdict()
    values = [value for key, value in groups.items() if key.startswith("value") and value]
    units = [value for key, value in groups.items() if key.startswith("unit") and value]
    value = values[-1].replace(",", "")
    unit = units[-1]
    if unit == "亿":
        unit = "亿元"
    return f"{value}{unit}", unit


@dataclass(frozen=True, slots=True)
class TableValue:
    value: str
    start: int
    end: int


def extract_numeric_values(line: str, *, fallback_unit: str | None) -> list[TableValue]:
    with_units = [
        TableValue(value=value_and_unit(match)[0], start=match.start(), end=match.end())
        for match in re.finditer(INLINE_VALUE_UNIT_PATTERN, line)
    ]
    if with_units or fallback_unit is None:
        return with_units
    raw_values: list[TableValue] = []
    for match in re.finditer(r"(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?![A-Za-z0-9])", line):
        value = match.group(1).replace(",", "")
        raw_values.append(TableValue(value=f"{value}{fallback_unit}", start=match.start(), end=match.end()))
    return raw_values


def clean_dimension(raw: str) -> str | None:
    cleaned = re.sub(r"[\s:：,，|]+", " ", raw).strip(" -_/|：:，,")
    cleaned = cleaned.replace("项目", "").replace("产品类别", "").strip()
    if not cleaned:
        return None
    return cleaned[-40:]


def metric_with_optional_dimension(metric_name: str, dimension: str | None) -> str:
    if metric_name not in {"revenue_segment", "production_capacity", "production_volume", "sales_volume"}:
        return metric_name
    cleaned = clean_dimension(dimension or "")
    return f"{metric_name}:{cleaned}" if cleaned else metric_name


def claim_label(metric_base: str, metric_name: str) -> str:
    label = METRIC_LABELS.get(metric_base, metric_base)
    if ":" not in metric_name:
        return label
    dimension = metric_name.split(":", 1)[1]
    return f"{dimension}{label}"
