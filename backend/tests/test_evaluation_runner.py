"""评测入口必须 fail closed，不允许缺数据时返回漂亮默认分数。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.runner import EvaluationRunner


def test_evaluation_runner_rejects_missing_datasets(tmp_path: Path) -> None:
    runner = EvaluationRunner(tmp_path)
    with pytest.raises(FileNotFoundError, match="fact_extraction_eval.json"):
        runner.run_all()


def test_evaluation_runner_rejects_empty_dataset(tmp_path: Path) -> None:
    (tmp_path / "fact_extraction_eval.json").write_text("[]", encoding="utf-8")
    runner = EvaluationRunner(tmp_path)
    with pytest.raises(ValueError, match="non-empty"):
        runner.run_fact_extraction_eval()


def test_evaluation_runner_uses_explicit_nonempty_datasets(tmp_path: Path) -> None:
    fact_items = [
        {
            "text": "2024年营业收入为10亿元",
            "expected": [{"metric_name": "revenue", "period": "2024", "value": "10亿元"}],
        }
    ]
    retrieval_items = [
        {
            "dense_ranked": ["relevant"],
            "sparse_ranked": ["relevant"],
            "relevant_chunk_ids": ["relevant"],
        }
    ]
    e2e_items = [{"required_sections": ["核心事实"], "sample_report": "核心事实"}]
    for name, items in [
        ("fact_extraction_eval.json", fact_items),
        ("retrieval_eval.json", retrieval_items),
        ("e2e_eval.json", e2e_items),
    ]:
        (tmp_path / name).write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    scores = EvaluationRunner(tmp_path).run_all()
    assert scores.fact_extraction_f1 == 1.0
    assert scores.retrieval_recall_at_10 == 1.0
    assert scores.e2e_quality == 1.0
