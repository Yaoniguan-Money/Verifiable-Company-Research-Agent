from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_BASE_URL = "http://localhost:8000"

FIXED_EVALUATION_CASES: dict[str, dict[str, Any]] = {
    "sample_hk_public_company_case": {
        "company_name": "小米集团",
        "stock_code": "01810",
        "question": (
            "请基于公开资料分析小米集团最近的经营风险和公开披露一致性，"
            "要求给出引用来源，不要给投资建议。"
        ),
        "status": "已真实验收",
    },
    "sample_hk_public_company_case_002": {
        "company_name": "腾讯控股",
        "stock_code": "00700",
        "question": (
            "请基于公开资料分析腾讯控股最近的经营风险和公开披露一致性，"
            "要求给出引用来源，不要给投资建议。"
        ),
        "status": "设计样例/待真实验收",
    },
    "sample_cn_public_company_case": {
        "company_name": "比亚迪",
        "stock_code": "002594/1211.HK",
        "question": (
            "请基于公开资料分析比亚迪最近的经营风险和公开披露一致性，"
            "要求给出引用来源，不要给投资建议。"
        ),
        "status": "设计样例/待真实验收",
    },
}


def _http_json(
    *,
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    data: bytes | None = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.URLError as exc:
        raise RuntimeError(f"请求失败：{method} {path}，请确认后端已启动。") from exc


def _list_fixed_cases() -> int:
    print("固定评测样例")
    print("这些真实公司样例只用于链路回归，不代表系统绑定特定企业，也不构成投资分析、评级、推荐或建议。")
    for case_id, info in FIXED_EVALUATION_CASES.items():
        print(
            f"- {case_id}: company_name={info['company_name']} "
            f"stock_code={info['stock_code']} status={info['status']}"
        )
    print("\n默认不执行全量真实样例，避免外部 API 成本与波动。")
    return 0


def _run_fixed_case(case_id: str, *, base_url: str) -> int:
    if case_id not in FIXED_EVALUATION_CASES:
        valid = ", ".join(sorted(FIXED_EVALUATION_CASES))
        raise SystemExit(f"未知 case: {case_id}。可选值：{valid}")

    case = FIXED_EVALUATION_CASES[case_id]
    providers = _http_json(base_url=base_url, method="GET", path="/health/providers", timeout_seconds=60.0)

    llm_provider = providers.get("llm_provider")
    search_provider = providers.get("search_provider")
    embedding_provider = providers.get("embedding_provider")
    embedding_model = providers.get("embedding_model")
    mock_enabled = bool(providers.get("mock_enabled"))
    print("=== Provider Health ===")
    print(f"llm_provider={llm_provider}")
    print(f"search_provider={search_provider}")
    print(f"embedding_provider={embedding_provider}")
    print(f"embedding_model={embedding_model}")
    print(f"mock_enabled={mock_enabled}")

    if mock_enabled:
        print("pass=false")
        print("reason=mock_enabled=true，当前不是真实链路模式")
        return 1

    if str(embedding_provider) != "dashscope" or str(embedding_model) != "text-embedding-v4":
        print("pass=false")
        print("reason=embedding provider/model 不符合真实链路基线")
        return 1

    task = _http_json(
        base_url=base_url,
        method="POST",
        path="/api/research/tasks",
        payload={"company_name": case["company_name"], "question": case["question"]},
        timeout_seconds=120.0,
    )
    task_id = str(task.get("task_id") or "")
    if not task_id:
        print("pass=false")
        print("reason=创建任务失败，响应中没有 task_id")
        return 1

    run_result = _http_json(
        base_url=base_url,
        method="POST",
        path=f"/api/research/tasks/{task_id}/run",
        timeout_seconds=600.0,
    )
    status = str(run_result.get("status") or "unknown")
    if status != "completed":
        error_text = str(run_result.get("error") or "unknown")
        print(f"case={case_id}")
        print(f"company_name={case['company_name']}")
        print(f"status={status}")
        print("pass=false")
        print(f"reason=任务失败，error={error_text}")
        return 1

    report = _http_json(
        base_url=base_url,
        method="GET",
        path=f"/api/research/tasks/{task_id}/report",
        timeout_seconds=120.0,
    )
    compliance_status = str(report.get("compliance_status") or "unknown")
    citations = report.get("citations") or []
    sources_resp = _http_json(base_url=base_url, method="GET", path=f"/api/sources/{task_id}", timeout_seconds=120.0)
    source_by_id = {str(item.get("id")): item for item in (sources_resp.get("items") or [])}

    source_layer_counts: dict[str, int] = {
        "official_pdf": 0,
        "official_disclosure_page": 0,
        "official_entry_page": 0,
        "third_party_background": 0,
        "low_authority": 0,
        "unknown": 0,
    }
    for citation in citations:
        source = source_by_id.get(str(citation.get("source_id") or ""), {})
        meta = source.get("source_metadata") or {}
        source_layer = str(meta.get("source_layer") or "unknown")
        source_layer_counts[source_layer] = source_layer_counts.get(source_layer, 0) + 1
        credibility = source.get("credibility_score")
        try:
            score = float(credibility) if credibility is not None else None
        except (TypeError, ValueError):
            score = None
        if score is not None and score < 0.6:
            source_layer_counts["low_authority"] += 1

    official_count = source_layer_counts.get("official_pdf", 0) + source_layer_counts.get(
        "official_disclosure_page", 0
    )
    low_authority_count = source_layer_counts.get("low_authority", 0)
    passed = status == "completed" and compliance_status == "passed" and official_count >= 1 and low_authority_count == 0
    reason = "ok" if passed else "不满足固定验收阈值（status/compliance/official/low_authority）"

    print(f"case={case_id}")
    print(f"company_name={case['company_name']}")
    print(f"status={status}")
    print(f"compliance_status={compliance_status}")
    print(f"source_layer_counts={json.dumps(source_layer_counts, ensure_ascii=False)}")
    print(f"official_count={official_count}")
    print(f"low_authority_count={low_authority_count}")
    print(f"pass={str(passed).lower()}")
    print(f"reason={reason}")
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public-company source regression smoke.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出固定评测样例，不触发真实 API 调用。",
    )
    parser.add_argument(
        "--case",
        choices=tuple(sorted(FIXED_EVALUATION_CASES)),
        help="只运行一个固定评测样例（默认不跑全量真实 API）。",
    )
    parser.add_argument(
        "--run-all-cases",
        action="store_true",
        help="顺序运行所有固定样例（会产生真实 API 成本，且可能受外部波动影响）。",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="后端服务地址，默认 http://localhost:8000。",
    )
    parser.add_argument(
        "--file",
        default="data/eval/public_company_regression.json",
        help="Regression case file.",
    )
    parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Use checked-in source fixtures instead of live public-source providers.",
    )
    parser.add_argument(
        "--fixtures-file",
        default="data/eval/public_company_regression_fixtures.json",
        help="Checked-in fixture source file.",
    )
    parser.add_argument(
        "--cache-file",
        default=None,
        help="Optional source cache file. If present, reuse it; otherwise fetch live and write it.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore existing --cache-file and fetch live sources again.",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Run lightweight fact extraction on fetched sources and print metric groups.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print quantitative suite score as JSON.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format. Defaults to text; markdown prints a compact summary table.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print quantitative suite score as a Markdown table.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=0.7,
        help="Minimum metric-group coverage ratio for each case.",
    )
    args = parser.parse_args()
    if args.list:
        raise SystemExit(_list_fixed_cases())

    if args.case:
        raise SystemExit(_run_fixed_case(args.case, base_url=str(args.base_url).rstrip("/")))

    if args.run_all_cases:
        print("[WARNING] 你正在运行所有固定真实样例，这会增加 API 成本且受外部波动影响。")
        exit_codes = [
            _run_fixed_case(case_id, base_url=str(args.base_url).rstrip("/"))
            for case_id in sorted(FIXED_EVALUATION_CASES)
        ]
        raise SystemExit(0 if all(code == 0 for code in exit_codes) else 1)

    print("[INFO] 默认进入离线回归模式（非固定真实样例）。使用 --list / --case 可走固定样例入口。")
    output_format = _resolve_output_format(args)

    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    from app.core.config import get_settings
    from app.evaluation import score_public_regression_case, score_public_regression_suite
    from app.providers.factory import ProviderFactory
    from app.schemas.retrieval import RetrievedEvidence
    from app.schemas.source import SourceCreate
    from app.services.fact_extraction import FactExtractionService

    provider = ProviderFactory(get_settings()).create_search_provider()
    case_scores = []
    fixture_sources = (
        _load_source_payload(Path(args.fixtures_file), SourceCreate) if args.use_fixtures else {}
    )
    cached_sources = (
        _load_source_payload(Path(args.cache_file), SourceCreate)
        if args.cache_file and Path(args.cache_file).exists() and not args.refresh_cache
        else {}
    )
    live_cache_output: dict[str, list[dict[str, Any]]] = {}

    for case in payload["cases"]:
        company = case["company_name"]
        question = case["question"]
        if output_format == "text":
            print(f"\n== {company} ==")
        if args.use_fixtures:
            sources = fixture_sources.get(company, [])
        elif company in cached_sources:
            sources = cached_sources[company]
        else:
            sources = provider.search(company, question)
            if args.cache_file:
                live_cache_output[company] = [_source_to_cache_item(source) for source in sources]
        if output_format == "text":
            print(f"sources={len(sources)}")
            for source in sources[:8]:
                print(f"- {source.source_type} score={source.credibility_score} title={source.title}")
                print(f"  {source.url}")
        facts = []
        metric_groups = []
        if args.extract:
            evidences = [
                RetrievedEvidence(
                    chunk_id=f"smoke_chunk_{idx}",
                    source_id=f"smoke_source_{idx}",
                    task_id="public_regression_smoke",
                    text=source.raw_content[:120_000],
                    score=1.0,
                    source_title=source.title,
                    source_url=source.url,
                    source_type=str(source.source_type),
                    retrieved_at=source.retrieved_at,
                    metadata=None,
                )
                for idx, source in enumerate(sources)
            ]
            facts = FactExtractionService().extract_from_retrieved_evidences(
                task_id="public_regression_smoke",
                company_name=company,
                question=question,
                evidences=evidences,
            ).facts
            metric_groups = sorted({(fact.metric_name or "").split(":", 1)[0] for fact in facts})
            if output_format == "text":
                print(f"facts={len(facts)} metric_groups={metric_groups}")
        case_score = score_public_regression_case(
            company_name=company,
            expected_metric_groups=case["expected_metric_groups"],
            observed_metric_groups=metric_groups,
            source_count=len(sources),
            fact_count=len(facts),
            minimum_coverage_ratio=args.fail_under,
        )
        case_scores.append(case_score)
        if args.extract and output_format == "text":
            print(
                "coverage="
                f"{case_score.metric_coverage_ratio:.2f} "
                f"missing={case_score.missing_metric_groups} "
                f"passed={case_score.passed}"
            )

    suite_score = score_public_regression_suite(case_scores)
    if output_format == "json":
        print(json.dumps(suite_score.to_dict(), ensure_ascii=False, indent=2))
    elif output_format == "markdown":
        print(suite_score.to_markdown())
    elif args.extract:
        print(
            "\nsummary: "
            f"passed={suite_score.passed_count}/{suite_score.case_count} "
            f"avg_coverage={suite_score.average_metric_coverage_ratio:.2f} "
            f"sources={suite_score.total_source_count} facts={suite_score.total_fact_count}"
        )

    if args.cache_file and live_cache_output:
        _write_source_cache(
            path=Path(args.cache_file),
            payload=payload,
            existing=cached_sources,
            live_output=live_cache_output,
        )

    if args.extract and not suite_score.passed:
        raise SystemExit(1)


def _resolve_output_format(args: argparse.Namespace) -> str:
    if args.json:
        return "json"
    if args.markdown:
        return "markdown"
    return str(args.output_format)


def _load_source_payload(path: Path, source_schema: type) -> dict[str, list[Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[Any]] = {}
    for case in payload.get("cases", []):
        company_name = case["company_name"]
        out[company_name] = [
            source_schema.model_validate(
                {
                    "task_id": "public_regression_fixture",
                    "title": item["title"],
                    "url": item.get("url"),
                    "source_type": item.get("source_type", "annual_report"),
                    "published_at": item.get("published_at"),
                    "retrieved_at": item["retrieved_at"],
                    "raw_content": item["raw_content"],
                    "credibility_score": item.get("credibility_score", 0.9),
                }
            )
            for item in case.get("sources", [])
        ]
    return out


def _source_to_cache_item(source: Any) -> dict[str, Any]:
    return {
        "title": source.title,
        "url": source.url,
        "source_type": getattr(source.source_type, "value", str(source.source_type)),
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "retrieved_at": source.retrieved_at.isoformat(),
        "raw_content": source.raw_content,
        "credibility_score": source.credibility_score,
    }


def _write_source_cache(
    *,
    path: Path,
    payload: dict[str, Any],
    existing: dict[str, list[Any]],
    live_output: dict[str, list[dict[str, Any]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for case in payload["cases"]:
        company = case["company_name"]
        if company in live_output:
            sources = live_output[company]
        else:
            sources = [_source_to_cache_item(source) for source in existing.get(company, [])]
        cases.append({"company_name": company, "sources": sources})
    path.write_text(
        json.dumps(
            {
                "version": payload.get("version"),
                "description": "Cached public-company regression sources. Do not commit secrets.",
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
