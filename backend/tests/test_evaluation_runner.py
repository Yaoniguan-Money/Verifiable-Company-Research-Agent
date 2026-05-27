"""评测脚本与数据集。"""

from __future__ import annotations

from pathlib import Path

from app.evaluation.runner import EvaluationRunner


def test_evaluation_runner_on_generated_datasets() -> None:
    root = Path(__file__).resolve().parents[2]
    runner = EvaluationRunner(root / "data" / "eval")
    scores = runner.run_all()
    assert scores.retrieval_recall_at_10 >= 0.9
    assert scores.e2e_quality >= 0.9
    assert 0.0 <= scores.fact_extraction_f1 <= 1.0
