"""升级计划评测入口：事实抽取 / 检索 / 端到端回归。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.evaluation.runner import EvaluationRunner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 VCRA 评测并输出 Markdown 报告")
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "eval" / "last_eval_report.md")
    args = parser.parse_args()

    eval_dir = ROOT / "data" / "eval"
    runner = EvaluationRunner(eval_dir)
    scores = runner.run_all()
    report = runner.generate_report(scores, threshold=args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(report)
    if not scores.passed(args.threshold):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
