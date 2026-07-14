"""Build a human-curated retrieval dataset from fixed synthetic company fixtures.

The query/label pairs below were authored independently of the retrieval
implementation.  Labels identify source lines by company and literal evidence
substring; the builder only resolves those annotations to stable chunk IDs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "eval" / "public_company_regression_fixtures.json"
OUTPUT = ROOT / "evidence" / "datasets" / "retrieval_curated_v1.json"


def spec(query: str, targets: list[tuple[str, str]], category: str, challenge: str) -> dict:
    return {"query": query, "targets": targets, "category": category, "challenge": challenge}


QUERY_SPECS = [
    spec("比亚迪最近三年的研发投入是多少", [("比亚迪", "研发费用")], "fact", "metric alias"),
    spec("比亚迪营业总收入趋势", [("比亚迪", "营业收入")], "fact", "abbreviation"),
    spec("比亚迪归母净利变化", [("比亚迪", "归属于上市公司股东的净利润")], "fact", "abbreviation"),
    spec("比亚迪汽车业务分部收入", [("比亚迪", "汽车、汽车相关产品")], "segment", "long label"),
    spec("比亚迪手机零部件业务收入", [("比亚迪", "手机部件")], "segment", "synonym"),
    spec("比亚迪乘用车能生产多少辆", [("比亚迪", "2025年乘用车产能"), ("比亚迪", "乘用车 产能状况")], "operations", "capacity paraphrase"),
    spec("比亚迪乘用车实际产出", [("比亚迪", "2025年乘用车产量"), ("比亚迪", "快报产量 430")], "operations", "production paraphrase"),
    spec("比亚迪乘用车卖了多少", [("比亚迪", "2025年乘用车销量"), ("比亚迪", "快报销量 420")], "operations", "sales paraphrase"),
    spec("比亚迪有哪些经营风险", [("比亚迪", "风险提示")], "risk", "broad question"),

    spec("云南白药研发支出走势", [("云南白药", "研发费用")], "fact", "metric alias"),
    spec("云南白药营收规模", [("云南白药", "营业收入")], "fact", "abbreviation"),
    spec("云南白药股东口径净利润", [("云南白药", "归属于上市公司股东的净利润")], "fact", "accounting boundary"),
    spec("云南白药药品板块收入", [("云南白药", "药品事业部收入")], "segment", "business segment"),
    spec("云南白药健康产品业务收入", [("云南白药", "健康品事业部收入")], "segment", "synonym"),
    spec("云南白药中药资源收入", [("云南白药", "中药资源事业部收入")], "segment", "business segment"),
    spec("云南白药渠道与政策风险", [("云南白药", "主要风险")], "risk", "multiple risk terms"),

    spec("宁德时代研发投入近三年数据", [("宁德时代", "研发费用")], "fact", "metric alias"),
    spec("宁德时代收入变化", [("宁德时代", "营业收入")], "fact", "short query"),
    spec("宁德时代归母利润", [("宁德时代", "归属于上市公司股东的净利润")], "fact", "abbreviation"),
    spec("宁德时代动力电池业务收入", [("宁德时代", "动力电池系统收入")], "segment", "product segment"),
    spec("宁德时代储能板块营收", [("宁德时代", "储能电池系统收入")], "segment", "abbreviation"),
    spec("宁德时代电池产能 GWh", [("宁德时代", "动力电池产能")], "operations", "unit token"),
    spec("宁德时代动力电池制造产量", [("宁德时代", "动力电池产量")], "operations", "production"),
    spec("宁德时代电池出货销量", [("宁德时代", "动力电池销量")], "operations", "sales synonym"),
    spec("宁德时代海外贸易和客户集中风险", [("宁德时代", "风险提示")], "risk", "compound risk"),

    spec("美的集团研发费用", [("美的集团", "研发费用")], "fact", "exact metric"),
    spec("美的集团总营收", [("美的集团", "营业收入")], "fact", "abbreviation"),
    spec("美的集团归属于母公司股东利润", [("美的集团", "归属于上市公司股东的净利润")], "fact", "long paraphrase"),
    spec("美的暖通空调收入", [("美的集团", "暖通空调收入")], "segment", "entity abbreviation"),
    spec("美的消费电器板块收入", [("美的集团", "消费电器收入")], "segment", "business segment"),
    spec("美的机器人自动化业务收入", [("美的集团", "机器人、自动化系统")], "segment", "punctuation"),
    spec("美的家用空调生产量", [("美的集团", "家用空调产量")], "operations", "production synonym"),
    spec("美的家用空调销售量", [("美的集团", "家用空调销量")], "operations", "sales synonym"),
    spec("美的汇率和海外经营风险", [("美的集团", "风险提示")], "risk", "compound risk"),

    spec("格力研发支出", [("格力电器", "研发费用")], "fact", "entity abbreviation"),
    spec("格力电器营业总收入", [("格力电器", "营业收入")], "fact", "exact entity"),
    spec("格力归母净利润", [("格力电器", "归属于上市公司股东的净利润")], "fact", "abbreviation"),
    spec("格力空调主营业务收入", [("格力电器", "空调业务收入")], "segment", "business synonym"),
    spec("格力生活家电收入", [("格力电器", "生活电器收入")], "segment", "synonym"),
    spec("格力工业产品收入", [("格力电器", "工业制品收入")], "segment", "synonym"),
    spec("格力空调产量", [("格力电器", "空调产量")], "operations", "production"),
    spec("格力空调销量", [("格力电器", "空调销量")], "operations", "sales"),
    spec("格力房地产后周期风险", [("格力电器", "风险提示")], "risk", "specific risk"),

    spec("五粮液营业收入", [("五粮液", "营业收入")], "fact", "exact metric"),
    spec("五粮液归母净利", [("五粮液", "归属于上市公司股东的净利润")], "fact", "abbreviation"),
    spec("五粮液核心产品收入", [("五粮液", "五粮液产品收入")], "segment", "core product paraphrase"),
    spec("五粮液系列酒营收", [("五粮液", "系列酒产品收入")], "segment", "abbreviation"),
    spec("五粮液其他酒类产品收入", [("五粮液", "酒类其他产品收入")], "segment", "word order"),
    spec("五粮液渠道库存与食品安全风险", [("五粮液", "风险提示")], "risk", "compound risk"),

    spec("比较比亚迪和宁德时代的研发投入", [("比亚迪", "研发费用"), ("宁德时代", "研发费用")], "cross-company", "multiple relevant chunks"),
    spec("比较美的与格力空调销量", [("美的集团", "家用空调销量"), ("格力电器", "空调销量")], "cross-company", "multiple entities"),
    spec("哪些公司提示了原材料价格波动风险", [("比亚迪", "风险提示"), ("云南白药", "主要风险"), ("美的集团", "风险提示"), ("格力电器", "风险提示")], "cross-company", "four relevant chunks"),
    spec("比亚迪员工总数", [], "negative", "answer absent"),
    spec("云南白药现金分红方案", [], "negative", "answer absent"),
    spec("宁德时代资产负债率", [], "negative", "answer absent"),
    spec("美的集团审计意见类型", [], "negative", "answer absent"),
    spec("格力电器碳排放总量", [], "negative", "answer absent"),
]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    chunks: list[dict] = []
    by_company: dict[str, list[dict]] = {}
    for case in source["cases"]:
        company = case["company_name"]
        lines = [line.strip() for line in case["sources"][0]["raw_content"].splitlines()]
        evidence_lines = [line for line in lines if line and not line.startswith("项目 ")]
        company_chunks: list[dict] = []
        for index, line in enumerate(evidence_lines, start=1):
            digest = hashlib.sha256(f"{company}\0{line}".encode()).hexdigest()[:10]
            chunk = {
                "id": f"chunk-{digest}",
                "company": company,
                "text": f"{company}：{line}",
                "source_url": case["sources"][0]["url"],
                "source_type": "synthetic annual-report fixture",
                "line_index": index,
            }
            chunks.append(chunk)
            company_chunks.append(chunk)
        by_company[company] = company_chunks

    queries: list[dict] = []
    for index, item in enumerate(QUERY_SPECS, start=1):
        relevant: list[str] = []
        for company, substring in item["targets"]:
            matches = [chunk["id"] for chunk in by_company[company] if substring in chunk["text"]]
            if not matches:
                raise RuntimeError(f"annotation target not found: {company} / {substring}")
            relevant.extend(matches)
        queries.append(
            {
                "id": f"q-{index:03d}",
                "query": item["query"],
                "relevant_chunk_ids": sorted(set(relevant)),
                "category": item["category"],
                "challenge": item["challenge"],
            }
        )

    if len(queries) < 50:
        raise RuntimeError("retrieval evidence dataset requires at least 50 queries")
    artifact = {
        "schema_version": 1,
        "dataset_id": "vcra-retrieval-curated-v1",
        "run_type": "offline fixture / synthetic source excerpts / human-curated labels",
        "source_file": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "annotation_method": (
            "Query and relevance targets were manually authored independently of retrieval code; "
            "the builder only resolves company+substring annotations to stable chunk IDs."
        ),
        "limitations": [
            "Source excerpts are synthetic regression fixtures, not verified current filings.",
            "Five negative queries have no relevant chunk; current retrieval does not abstain.",
            "No labels were removed after observing retrieval results.",
        ],
        "corpus": chunks,
        "queries": queries,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"chunks": len(chunks), "queries": len(queries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
