"""Build fact-extraction labels from fixed table excerpts using an independent schema map.

This script intentionally imports no extraction implementation.  The annotation
map below expresses the table semantics directly and retains negative/risk rows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_DATASET = ROOT / "evidence" / "datasets" / "retrieval_curated_v1.json"
OUTPUT = ROOT / "evidence" / "datasets" / "fact_extraction_curated_v1.json"
YEARS = ["2025", "2024", "2023"]
VALUE_RE = re.compile(r"\d+(?:\.\d+)?(?:亿元|GWh|万辆|万台)")


def metric_family(line: str) -> str | None:
    if "研发费用" in line:
        return "R&D_expenditure"
    if "归属于上市公司股东的净利润" in line:
        return "net_profit_parent"
    if "营业收入" in line:
        return "revenue"
    if "产能" in line:
        return "production_capacity"
    if "产量" in line:
        return "production_volume"
    if "销量" in line:
        return "sales_volume"
    if "收入" in line:
        return "revenue_segment"
    return None


def annotate(line: str) -> list[dict]:
    if "风险" in line:
        return []
    values = VALUE_RE.findall(line)
    if not values:
        return []

    if all(marker in line for marker in ["产能状况", "快报产量", "快报销量", "销售收入"]):
        annotations = []
        for marker, family in [
            ("产能状况", "production_capacity"),
            ("快报产量", "production_volume"),
            ("快报销量", "sales_volume"),
            ("销售收入", "revenue_segment"),
        ]:
            match = re.search(rf"{marker}\s*(\d+(?:\.\d+)?(?:亿元|GWh|万辆|万台))", line)
            if not match:
                raise RuntimeError(f"wide-row annotation failed for {marker}: {line}")
            annotations.append({"metric_family": family, "period": "2025", "value": match.group(1)})
        return annotations

    family = metric_family(line)
    if family is None:
        return []
    explicit_year = re.search(r"(20\d{2})年", line)
    if explicit_year and len(values) == 1:
        return [{"metric_family": family, "period": explicit_year.group(1), "value": values[0]}]
    return [
        {"metric_family": family, "period": year, "value": value}
        for year, value in zip(YEARS, values, strict=False)
    ]


def main() -> None:
    retrieval = json.loads(RETRIEVAL_DATASET.read_text(encoding="utf-8"))
    items = []
    for chunk in retrieval["corpus"]:
        line = chunk["text"].split("：", 1)[1]
        expected = annotate(line)
        text = line if not expected else f"项目 2025年 2024年 2023年\n{line}"
        items.append(
            {
                "id": f"fact-{chunk['id']}",
                "company_name": chunk["company"],
                "text": text,
                "expected": expected,
                "sample_type": "negative" if not expected else ("multi-fact" if len(expected) > 1 else "single-fact"),
                "source_chunk_id": chunk["id"],
            }
        )
    if len(items) < 50:
        raise RuntimeError("fact extraction dataset requires at least 50 annotated samples")
    artifact = {
        "schema_version": 1,
        "dataset_id": "vcra-fact-extraction-curated-v1",
        "run_type": "offline fixture / synthetic source excerpts / independently mapped labels",
        "annotation_method": (
            "A manually authored phrase-to-metric-family map and fixed table-column semantics; "
            "the builder imports no fact-extraction code and labels were frozen before evaluation."
        ),
        "limitations": [
            "Synthetic financial excerpts, not verified current filings.",
            "Evaluation compares metric family, period, and unit-normalized value; it does not score dimension wording.",
            "Risk rows are retained as negative samples.",
        ],
        "items": items,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"items": len(items), "expected_facts": sum(len(item["expected"]) for item in items)}))


if __name__ == "__main__":
    main()
