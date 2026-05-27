"""生成评测集：事实抽取 200 / 检索 50 / 端到端 20。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"


def _fact_items() -> list[dict]:
    templates = [
        ("2024年研发投入为309.40亿元", "R&D_expenditure", "2024", "309.40亿元"),
        ("2024年营业收入为7771.02亿元", "revenue", "2024", "7771.02亿元"),
        ("2023年净利润为302.44亿元", "net_profit", "2023", "302.44亿元"),
        ("经营活动产生的现金流量净额为1697.25亿元", "operating_cash_flow", "2024", "1697.25亿元"),
    ]
    items: list[dict] = []
    for i in range(200):
        snippet, metric, period, value = templates[i % len(templates)]
        text = f"公司披露{period}年度相关指标，{snippet}。"
        items.append(
            {
                "id": f"fact_{i:03d}",
                "company_name": "样例科技",
                "question": "财务与研发投入",
                "text": text,
                "expected": [{"metric_name": metric, "period": period, "value": value}],
            }
        )
    return items


def _retrieval_items() -> list[dict]:
    items = []
    for i in range(50):
        rel = [f"chunk_rel_{i}", f"chunk_rel_{i}_b"]
        items.append(
            {
                "query": f"样例公司 {i} 研发投入与经营风险",
                "dense_ranked": [f"chunk_noise_{i}", rel[0], rel[1]],
                "sparse_ranked": [rel[1], f"chunk_noise_{i}a", rel[0]],
                "relevant_chunk_ids": rel,
            }
        )
    return items


def _e2e_items() -> list[dict]:
    sections = ["## 核心事实", "## 可信度说明", "## 证据摘录"]
    return [
        {
            "id": f"e2e_{i:02d}",
            "company_name": f"公司{i}",
            "question": "近三年研发投入与风险",
            "required_sections": sections,
            "sample_report": "\n".join(sections) + "\n内容占位",
        }
        for i in range(20)
    ]


def main() -> None:
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "fact_extraction_eval.json").write_text(
        json.dumps(_fact_items(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (EVAL / "retrieval_eval.json").write_text(
        json.dumps(_retrieval_items(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (EVAL / "e2e_eval.json").write_text(
        json.dumps(_e2e_items(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已写入评测集到 {EVAL}")


if __name__ == "__main__":
    main()
