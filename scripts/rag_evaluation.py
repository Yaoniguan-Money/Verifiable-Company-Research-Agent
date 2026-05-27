#!/usr/bin/env python3
"""RAG Pipeline 全面评测脚本：自动化测试研究任务并生成量化报告。"""

import json
import time
import urllib.request
from dataclasses import dataclass, field

API = "http://localhost:8000/api"


def api(path, method="GET", body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json") if body else None
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


@dataclass
class TestCase:
    company: str
    question: str
    expected_metric: str | None = None
    expected_value_range: tuple[float, float] | None = None  # (min_billion, max_billion) in 亿元
    note: str = ""


GROUND_TRUTH = {
    # 格式: (company_name, question) → (expected_metric, min_billion, max_billion)
    # 以下为占位示例数据，请替换为你自己的评测用例。
    # ("某A股上市公司", "2025研发投入"): ("R&D_total_spending", 600, 660),
}



TEST_CASES = [
    # 请填写你自己的评测用例。
    # TestCase("某A股上市公司", "2025研发投入", note="核心R&D指标"),
]



@dataclass
class TestResult:
    case: TestCase
    task_id: str = ""
    status: str = ""
    duration_sec: float = 0
    facts_total: int = 0
    facts_verified: int = 0
    facts_conflicted: int = 0
    primary_facts: list[str] = field(default_factory=list)
    answer_text: str = ""
    metric_match: bool = False
    value_in_range: bool = False
    extracted_value: str = ""
    errors: list[str] = field(default_factory=list)


def run_test(case: TestCase, timeout_sec: int = 120) -> TestResult:
    result = TestResult(case=case)
    t0 = time.time()

    try:
        # Create task
        task = api("/research/tasks", "POST", {
            "company_name": case.company,
            "question": case.question,
        })
        result.task_id = task["task_id"]

        # Run workflow (synchronous)
        outcome = api(f"/research/tasks/{result.task_id}/run", "POST")
        result.status = outcome.get("status", "unknown")

        # Get report
        report = api(f"/reports/{result.task_id}")
        content = report.get("content", "")

        # Get facts
        facts_data = api(f"/facts/{result.task_id}")
        facts = facts_data if isinstance(facts_data, list) else facts_data.get("items", [])

        # Get verification
        ver_data = api(f"/verification/{result.task_id}")
        vers = ver_data if isinstance(ver_data, list) else ver_data.get("items", [])

        result.facts_total = len(facts)
        result.facts_verified = sum(1 for v in vers if str(v.get("status", "")).lower() == "verified")
        result.facts_conflicted = sum(1 for v in vers if str(v.get("status", "")).lower() == "conflicted")

        # Extract core findings
        in_core = False
        for line in content.split("\n"):
            if line.startswith("- ") and ("亿元" in line or "千元" in line or "万元" in line):
                result.primary_facts.append(line.strip("- "))
                in_core = True
            elif in_core and not line.startswith("- "):
                in_core = False

        result.answer_text = content

        # Check against ground truth
        gt = GROUND_TRUTH.get((case.company, case.question))
        if gt:
            expected_metric, min_val, max_val = gt
            for f in facts:
                # Check metric match
                mn = (f.get("metric_name") or "").lower()
                if expected_metric.lower() in mn or expected_metric.lower().replace("_","") in mn.replace("_",""):
                    val_str = f.get("value", "")
                    # Convert to billions (亿元)
                    try:
                        if "千元" in val_str:
                            num = float("".join(c for c in val_str.replace("千元","") if c.isdigit() or c == "."))
                            billions = num / 10000
                        elif "元" in val_str and "亿元" not in val_str:
                            num = float("".join(c for c in val_str.replace("元","") if c.isdigit() or c == "."))
                            billions = num / 100_000_000
                        elif "亿元" in val_str:
                            num = float("".join(c for c in val_str.replace("亿元","") if c.isdigit() or c == "."))
                            billions = num
                        else:
                            continue
                        result.metric_match = True
                        result.extracted_value = f"{billions:.2f}亿元"
                        if min_val <= billions <= max_val:
                            result.value_in_range = True
                    except ValueError:
                        pass

    except Exception as e:
        result.errors.append(str(e))
        result.status = "error"

    result.duration_sec = round(time.time() - t0, 1)
    return result


def print_report(results: list[TestResult]):
    print("=" * 80)
    print("RAG PIPELINE 全面评测报告")
    print("=" * 80)
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试用例数: {len(results)}")
    print()

    # Summary stats
    passed_metric = sum(1 for r in results if r.metric_match)
    passed_value = sum(1 for r in results if r.value_in_range)
    avg_duration = sum(r.duration_sec for r in results if r.duration_sec > 0) / max(1, len([r for r in results if r.duration_sec > 0]))
    avg_facts = sum(r.facts_total for r in results) / max(1, len(results))
    avg_verified = sum(r.facts_verified for r in results) / max(1, len(results))

    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│                           核心指标概览                                      │")
    print("├──────────────────────────┬──────────────────────────────────────────────────┤")
    print(f"│ 指标匹配率               │ {passed_metric}/{len(results)} ({passed_metric*100//max(1,len(results))}%)                                        │")
    print(f"│ 数值准确率 (在预期范围内) │ {passed_value}/{len(results)} ({passed_value*100//max(1,len(results))}%)                                        │")
    print(f"│ 平均任务耗时             │ {avg_duration:.1f}s                                              │")
    print(f"│ 平均抽取事实数           │ {avg_facts:.0f}                                                │")
    print(f"│ 平均校验通过数           │ {avg_verified:.0f}                                                │")
    print("└──────────────────────────┴──────────────────────────────────────────────────┘")
    print()

    # Per-case details
    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│                           逐用例详情                                        │")
    print("├──────┬──────────┬───────────────┬────────┬────────┬────────┬───────────────┤")
    print("│ 状态 │ 公司     │ 问题          │ 耗时   │ 事实数 │ 验证数 │ 提取值        │")
    print("├──────┼──────────┼───────────────┼────────┼────────┼────────┼───────────────┤")
    for r in results:
        status = "PASS" if r.metric_match and r.value_in_range else ("PART" if r.metric_match else "FAIL")
        print(f"│ {status:4s} │ {r.case.company:8s} │ {r.case.question:13s} │ {r.duration_sec:5.0f}s │ {r.facts_total:6d} │ {r.facts_verified:6d} │ {r.extracted_value:13s} │")
    print("└──────┴──────────┴───────────────┴────────┴────────┴────────┴───────────────┘")
    print()

    # RAG pipeline component analysis
    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│                       RAG 管线组件分析                                      │")
    print("├──────────────────────────┬──────────────────────────────────────────────────┤")
    print("│ 组件                    │ 状态 / 评估                                       │")
    print("├──────────────────────────┼──────────────────────────────────────────────────┤")

    # Check components
    # Source collection
    source_failures = sum(1 for r in results if "source" in " ".join(r.errors).lower() or r.status == "failed")
    print(f"│ 来源采集 (Source Coll.)  │ {'PASS' if source_failures == 0 else 'FAIL'}: {len(results)-source_failures}/{len(results)} 成功                               │")

    # Chunking
    chunk_issues = sum(1 for r in results if r.facts_total == 0 and r.errors)
    print(f"│ 分块入库 (Ingestion)     │ {'PASS' if chunk_issues == 0 else 'ISSUE'}: 平均 {avg_facts:.0f} facts/task                         │")

    # LLM extraction effectiveness
    llm_fact_tasks = sum(1 for r in results if r.metric_match and r.value_in_range)
    print(f"│ LLM 抽取 (LLM Extraction)│ {'PASS' if llm_fact_tasks >= len(results)//2 else 'PARTIAL'}: {llm_fact_tasks}/{len(results)} 指标匹配                              │")

    # Verification
    ver_quality = "GOOD" if avg_verified > 0 else "POOR"
    print(f"│ 校验层 (Verification)    │ {ver_quality}: 平均 {avg_verified:.0f} verified/task                            │")

    # Answer quality
    answer_quality = "GOOD" if passed_value >= len(results) // 2 else "NEEDS WORK"
    print(f"│ 答案质量 (Answer Quality) │ {answer_quality}: {passed_value}/{len(results)} 值在预期范围                            │")
    print("└──────────────────────────┴──────────────────────────────────────────────────┘")
    print()

    # Improvements summary
    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│                    本会话已修复的关键问题                                    │")
    print("├────┬────────────────────────────────────────────────────────────────────────┤")
    print("│ #  │ 修复内容                                                               │")
    print("├────┼────────────────────────────────────────────────────────────────────────┤")
    fixes = [
        ("1", "NUMBER_PATTERN 支持空格分位符 (371 280 948 000.00)"),
        ("2", "表格提取新增利润行识别 (net_profit_parent/deducted/net_profit)"),
        ("3", "校验层 unit_normalized 消除元/亿元虚假冲突"),
        ("4", "FACT_RULES 连接词扩展：约人民币/约/人民币"),
        ("5", "研发费用 vs 研发投入合计 拆分为独立 metric (R&D_expenditure/R&D_total_spending)"),
        ("6", "答案管道：conflicted 事实回退 + 首选指标优先 + LLM 事实置信度=1.0"),
        ("7", "LLM Prompt 标准化：metric_name 映射表 + period/format 规则 + 后处理归一化"),
        ("8", "Chunk 排序 LLM 抽取：Embedding 语义排序 + 依次送检 + 意图命中即停"),
        ("9", "多 Agent 框架移除：删除 5 个空壳 Agent，清理 1000+ 行代码"),
        ("10", "EmbeddingReranker：复用 DashScope API 替代词面 Jaccard 重排序"),
        ("11", "PgVector HNSW 维度硬编码修复 (vector(1024)→vector)"),
        ("12", "对比功能并行化 + Session 隔离 + 报告话术优化"),
    ]
    for num, desc in fixes:
        print(f"│ {num}  │ {desc:<70} │")
    print("└────┴────────────────────────────────────────────────────────────────────────┘")
    print()
    print("=" * 80)
    print("评测完成。")
    print("=" * 80)


if __name__ == "__main__":
    results = []
    for i, case in enumerate(TEST_CASES):
        print(f"[{i+1}/{len(TEST_CASES)}] 测试: {case.company} - {case.question} ...", end=" ", flush=True)
        result = run_test(case)
        results.append(result)
        status = "PASS" if result.metric_match and result.value_in_range else ("PARTIAL" if result.metric_match else "FAIL")
        print(f"{status} ({result.duration_sec}s, {result.facts_total} facts, value={result.extracted_value})")

    print()
    print_report(results)
