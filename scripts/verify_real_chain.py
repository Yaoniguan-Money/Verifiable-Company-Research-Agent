"""Real-provider chain verification script.

The script intentionally prints only provider metadata and citation distribution.
It never prints API keys or raw environment values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_COMPANY = "Sample Public Company"
DEFAULT_QUESTION = (
    "请基于公开资料分析该企业最近的经营风险和公开披露一致性，"
    "要求优先使用公司官网、交易所公告、年报、半年报、监管披露等权威来源，不要给投资建议。"
)


@dataclass(frozen=True)
class VerifyResult:
    task_id: str
    report_id: str | None
    status: str
    compliance_status: str | None
    title: str | None
    citation_count: int
    layer_counts: dict[str, int]


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    base_url: str,
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


def assert_embedding_mode_for_real_chain(
    providers: dict[str, Any], *, allow_local_embedding: bool
) -> None:
    """Strict real-chain checks reject local_hashing unless explicitly waived."""
    ep = str(providers.get("embedding_provider") or "")
    if ep != "local_hashing":
        return
    msg = (
        "local_hashing is for dev/test and is not a real semantic embedding provider. "
        "真实语义验收请使用 EMBEDDING_PROVIDER=dashscope 并配置 EMBEDDING_API_KEY。"
    )
    if allow_local_embedding:
        print(f"\n[WARNING] {msg}\n")
        return
    raise RuntimeError(msg)


def verify_real_chain(
    *,
    allow_local_embedding: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    company_name: str = DEFAULT_COMPANY,
    question: str = DEFAULT_QUESTION,
) -> VerifyResult:
    normalized_base_url = normalize_base_url(base_url)
    providers = _request("GET", "/health/providers", base_url=normalized_base_url)
    llm_provider = providers.get("llm_provider")
    search_provider = providers.get("search_provider")
    embedding_provider = providers.get("embedding_provider")
    embedding_model = providers.get("embedding_model")
    embedding_base_url_host = providers.get("embedding_base_url_host")
    embedding_max_batch_size = providers.get("embedding_max_batch_size")
    emb_key_ok = providers.get("embedding_api_key_configured")
    mock_enabled = bool(providers.get("mock_enabled"))

    print("=== Provider Health ===")
    print(f"llm_provider={llm_provider}")
    print(f"search_provider={search_provider}")
    print(f"embedding_provider={embedding_provider}")
    print(f"embedding_model={embedding_model}")
    print(f"embedding_base_url_host={embedding_base_url_host}")
    print(f"embedding_max_batch_size={embedding_max_batch_size}")
    print(f"embedding_api_key_configured={emb_key_ok}")
    print(f"mock_enabled={mock_enabled}")

    assert_embedding_mode_for_real_chain(providers, allow_local_embedding=allow_local_embedding)

    if mock_enabled:
        raise RuntimeError("mock_enabled=true，当前不是真实链路验收模式。")

    task = _request(
        "POST",
        "/api/research/tasks",
        {"company_name": company_name, "question": question},
        base_url=normalized_base_url,
        timeout_seconds=120.0,
    )
    task_id = str(task.get("task_id") or "")
    if not task_id:
        raise RuntimeError("创建任务失败：响应中没有 task_id。")

    run_result = _request(
        "POST",
        f"/api/research/tasks/{task_id}/run",
        base_url=normalized_base_url,
        timeout_seconds=600.0,
    )
    status = str(run_result.get("status") or "unknown")
    report_id = run_result.get("report_id")
    if status != "completed":
        # External APIs can time out or close connections. The verifier reports that
        # clearly, but never converts a failed real run into a successful mock run.
        error_text = str(run_result.get("error") or "unknown")
        node = _infer_failed_node(error_text)
        instability = "yes" if _is_external_provider_instability(error_text) else "no"
        raise RuntimeError(
            "任务运行失败："
            f"status={status}, failed_node={node}, "
            f"external_provider_or_network_instability={instability}, "
            f"error={error_text}"
        )

    report = _request(
        "GET",
        f"/api/research/tasks/{task_id}/report",
        base_url=normalized_base_url,
        timeout_seconds=120.0,
    )
    citations = report.get("citations") or []
    if not citations:
        raise RuntimeError("报告没有 citations，无法完成真实链路验收。")

    sources_resp = _request("GET", f"/api/sources/{task_id}", base_url=normalized_base_url)
    source_by_id = {str(item.get("id")): item for item in (sources_resp.get("items") or [])}

    layer_counts = {
        "official_pdf": 0,
        "official_disclosure_page": 0,
        "official_entry_page": 0,
        "third_party_background": 0,
        "low_authority": 0,
        "unknown": 0,
    }

    print("\n=== Citation Preview ===")
    for idx, citation in enumerate(citations, start=1):
        source_id = str(citation.get("source_id") or "")
        source = source_by_id.get(source_id, {})
        source_metadata = source.get("source_metadata") or {}
        source_layer = str(source_metadata.get("source_layer") or "unknown")
        authority = _authority_label(source.get("credibility_score"))
        if source_layer in layer_counts:
            layer_counts[source_layer] += 1
        else:
            layer_counts["unknown"] += 1
        if authority == "low_authority":
            layer_counts["low_authority"] += 1

        if idx <= 8:
            print(
                f"[{idx}] title={citation.get('title')} | "
                f"url={citation.get('url')} | "
                f"source_layer={source_layer} | authority={authority}"
            )

    return VerifyResult(
        task_id=task_id,
        report_id=str(report_id) if report_id is not None else None,
        status=status,
        compliance_status=report.get("compliance_status"),
        title=report.get("title"),
        citation_count=len(citations),
        layer_counts=layer_counts,
    )


def _authority_label(score: Any) -> str:
    if score is None:
        return "unknown"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 0.85:
        return "high_authority"
    if value < 0.6:
        return "low_authority"
    return "medium_authority"


def normalize_base_url(value: str) -> str:
    """Normalize a backend base URL accepted by CLI/env config."""
    url = str(value or "").strip().rstrip("/")
    if not url:
        raise ValueError("base_url must not be blank")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("base_url must start with http:// or https://")
    return url


def _infer_failed_node(error_text: str) -> str:
    lower = error_text.lower()
    for node in (
        "collect_sources_node",
        "source_quality_gate_node",
        "ingest_chunks_node",
        "embed_chunks_node",
        "retrieve_evidence_node",
        "extract_facts_node",
        "verify_facts_node",
        "analyze_risks_node",
        "build_report_node",
        "compliance_check_node",
        "persist_result_node",
    ):
        if node in lower:
            return node
    return "unknown"


def _is_external_provider_instability(error_text: str) -> bool:
    lower = error_text.lower()
    markers = (
        "readtimeout",
        "read timeout",
        "timeout",
        "remote end closed connection",
        "connection reset",
        "temporarily unavailable",
        "connection aborted",
    )
    return any(item in lower for item in markers)


def main() -> int:
    parser = argparse.ArgumentParser(description="真实链路一键验收（不打印密钥）。")
    parser.add_argument(
        "--allow-local-embedding",
        action="store_true",
        help="允许在 EMBEDDING_PROVIDER=local_hashing 时继续执行（仅开发用，仍会 warning）。",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("VERIFY_BASE_URL", DEFAULT_BASE_URL),
        help="后端服务地址。也可用 VERIFY_BASE_URL 设置。默认 http://localhost:8000。",
    )
    parser.add_argument(
        "--company-name",
        default=os.getenv("VERIFY_COMPANY_NAME", DEFAULT_COMPANY),
        help="待验收公司名称。默认使用中性占位，真实验收建议显式传入。",
    )
    parser.add_argument(
        "--question",
        default=os.getenv("VERIFY_QUESTION", DEFAULT_QUESTION),
        help="研究问题。不要包含投资建议、目标价或收益预测请求。",
    )
    args = parser.parse_args()
    try:
        result = verify_real_chain(
            allow_local_embedding=args.allow_local_embedding,
            base_url=str(args.base_url),
            company_name=str(args.company_name),
            question=str(args.question),
        )
    except Exception as first_exc:  # noqa: BLE001
        first_text = str(first_exc)
        print(f"\n[FAILED][attempt=1] {first_text}")
        print("[INFO] first attempt failed, retrying once ...")
        try:
            result = verify_real_chain(
                allow_local_embedding=args.allow_local_embedding,
                base_url=str(args.base_url),
                company_name=str(args.company_name),
                question=str(args.question),
            )
        except Exception as second_exc:  # noqa: BLE001
            second_text = str(second_exc)
            instability = "yes" if _is_external_provider_instability(second_text) else "no"
            failed_node = _infer_failed_node(second_text)
            print(
                "\n[FAILED][attempt=2] "
                f"failed_node={failed_node} "
                f"external_provider_or_network_instability={instability} "
                f"error={second_text}"
            )
            return 1
        print("[INFO] retry succeeded.")

    print("\n=== Verify Result ===")
    print(f"task_id={result.task_id}")
    print(f"report_id={result.report_id}")
    print(f"status={result.status}")
    print(f"compliance_status={result.compliance_status}")
    print(f"title={result.title}")
    print(f"citation_count={result.citation_count}")
    print("source_layer_counts=")
    for key, value in result.layer_counts.items():
        print(f"  {key}: {value}")
    print("\n[OK] 真实链路验收脚本执行完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
