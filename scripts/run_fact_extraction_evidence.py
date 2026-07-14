"""Run fact extraction precision/recall/F1 on the frozen curated dataset."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.schemas.chunk import EvidenceChunkRead  # noqa: E402
from app.services.fact_extraction import FactExtractionService  # noqa: E402
from app.services.fact_metric_normalization import FactMetricNormalizer  # noqa: E402
from app.services.fact_value_normalization import FactValueNormalizer  # noqa: E402

DATASET = ROOT / "evidence" / "datasets" / "fact_extraction_curated_v1.json"
RAW = ROOT / "evidence" / "raw" / "fact_extraction_benchmark.json"
FAILURES = ROOT / "evidence" / "failures" / "fact_extraction_failures.json"
REPORT = ROOT / "evidence" / "reports" / "fact_extraction_benchmark.md"
SIMPLE_VALUE_RE = re.compile(r"\d+(?:\.\d+)?(?:亿元|GWh|万辆|万台)")


def family(metric: str, normalizer: FactMetricNormalizer) -> str:
    return normalizer.comparable_key(metric).split(":", 1)[0]


def simple_regex_baseline(text: str, value_normalizer: FactValueNormalizer) -> set[tuple[str, str, str]]:
    """A deliberately simple solution: one recognized fact and first numeric value per chunk."""
    if "风险" in text:
        return set()
    mappings = [
        ("研发费用", "R&D_expenditure"),
        ("归属于上市公司股东的净利润", "net_profit_parent"),
        ("营业收入", "revenue"),
        ("产能", "production_capacity"),
        ("产量", "production_volume"),
        ("销量", "sales_volume"),
        ("收入", "revenue_segment"),
    ]
    metric = next((name for phrase, name in mappings if phrase in text), None)
    year = re.search(r"(20\d{2})年", text)
    value = SIMPLE_VALUE_RE.search(text)
    if not metric or not year or not value:
        return set()
    return {(metric, year.group(1), value_normalizer.comparable_key(value.group(0)))}


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    metric_normalizer = FactMetricNormalizer()
    value_normalizer = FactValueNormalizer()
    service = FactExtractionService()
    rows = []
    total_tp = total_fp = total_fn = 0
    baseline_tp = baseline_fp = baseline_fn = 0

    for item in dataset["items"]:
        chunk = EvidenceChunkRead(
            id=item["source_chunk_id"],
            source_id=f"source-{item['source_chunk_id']}",
            task_id="fact-evidence-task",
            chunk_index=0,
            text=item["text"],
            metadata={},
            embedding_id=None,
            created_at=datetime.now(timezone.utc),
        )
        result = service.extract_from_chunks(
            task_id="fact-evidence-task",
            company_name=item["company_name"],
            question="研发、收入、利润、分业务收入、产能、产量和销量",
            chunks=[chunk],
        )
        predicted = {
            (
                family(fact.metric_name or "", metric_normalizer),
                (fact.period or "").strip(),
                value_normalizer.comparable_key(fact.value),
            )
            for fact in result.facts
        }
        expected = {
            (
                annotation["metric_family"],
                annotation["period"],
                value_normalizer.comparable_key(annotation["value"]),
            )
            for annotation in item["expected"]
        }
        baseline_predicted = simple_regex_baseline(item["text"], value_normalizer)
        row_baseline_tp = len(baseline_predicted & expected)
        row_baseline_fp = len(baseline_predicted - expected)
        row_baseline_fn = len(expected - baseline_predicted)
        baseline_tp += row_baseline_tp
        baseline_fp += row_baseline_fp
        baseline_fn += row_baseline_fn
        tp = len(predicted & expected)
        fp = len(predicted - expected)
        fn = len(expected - predicted)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        rows.append(
            {
                "id": item["id"],
                "sample_type": item["sample_type"],
                "text": item["text"],
                "expected": sorted(expected),
                "baseline_predicted": sorted(baseline_predicted),
                "predicted": sorted(predicted),
                "baseline_tp": row_baseline_tp,
                "baseline_fp": row_baseline_fp,
                "baseline_fn": row_baseline_fn,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }
        )

    baseline_precision = baseline_tp / (baseline_tp + baseline_fp) if baseline_tp + baseline_fp else 0.0
    baseline_recall = baseline_tp / (baseline_tp + baseline_fn) if baseline_tp + baseline_fn else 0.0
    baseline_f1 = (
        2 * baseline_precision * baseline_recall / (baseline_precision + baseline_recall)
        if baseline_precision + baseline_recall else 0.0
    )
    precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negative_rows = [row for row in rows if row["sample_type"] == "negative"]
    summary = {
        "samples": len(rows),
        "expected_facts": total_tp + total_fn,
        "predicted_facts": total_tp + total_fp,
        "baseline": {
            "description": "single recognized metric + first numeric value per chunk",
            "tp": baseline_tp,
            "fp": baseline_fp,
            "fn": baseline_fn,
            "precision": baseline_precision,
            "recall": baseline_recall,
            "f1": baseline_f1,
        },
        "current": {
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "changes": {"f1_pp": (f1 - baseline_f1) * 100},
        "negative_samples": len(negative_rows),
        "negative_false_positive_rate": (
            sum(1 for row in negative_rows if row["predicted"]) / len(negative_rows)
            if negative_rows else 0.0
        ),
    }
    failures = [row for row in rows if row["fp"] or row["fn"]]
    artifact = {
        "schema_version": 1,
        "run_type": dataset["run_type"],
        "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
        "metric_definition": "micro exact match on (normalized metric family, period, unit-normalized value)",
        "summary": summary,
        "results": rows,
    }
    for path in [RAW, FAILURES, REPORT]:
        path.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    FAILURES.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(
        "# Fact extraction benchmark\n\n"
        f"Run type: {dataset['run_type']}.\n\n"
        f"- Samples: {summary['samples']}; expected facts: {summary['expected_facts']}\n"
        f"- Simple regex baseline P/R/F1: {baseline_precision:.3f} / {baseline_recall:.3f} / {baseline_f1:.3f}\n"
        f"- Current P/R/F1: {precision:.3f} / {recall:.3f} / {f1:.3f}\n"
        f"- F1 change: {(f1-baseline_f1)*100:+.2f} percentage points\n"
        f"- Current TP / FP / FN: {total_tp} / {total_fp} / {total_fn}\n"
        f"- Negative-sample false-positive rate: {summary['negative_false_positive_rate']:.1%}\n"
        f"- Failure samples retained: {len(failures)}\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
