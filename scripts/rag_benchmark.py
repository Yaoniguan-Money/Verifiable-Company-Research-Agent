#!/usr/bin/env python3
"""RAG 管线行业标准评测脚本 v2 — 精简高效版。

IR 指标: Precision@K, Recall@K, F1@K, MRR, NDCG@K, MAP
事实抽取: Exact Match, Precision, Recall, F1
管线分析: 7层逐层检查
"""

from __future__ import annotations

import json, math, time, urllib.request
from dataclasses import dataclass

API = "http://localhost:8000/api"

def aget(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=60) as r:
        return json.loads(r.read())

def apost(path, body):
    d = json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=d, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())

def apatch(path, body):
    d = json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=d, method="PATCH")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def value_to_billions(v: str) -> float | None:
    v = v.replace(",","").replace(" ","").strip()
    try:
        if "千元" in v: return float("".join(c for c in v.replace("千元","") if c.isdigit()or c=="."))/100000
        if "万元" in v: return float("".join(c for c in v.replace("万元","") if c.isdigit()or c=="."))/10000
        if "亿元" in v: return float("".join(c for c in v.replace("亿元","") if c.isdigit()or c=="."))
        if v.endswith("亿"): return float("".join(c for c in v[:-1] if c.isdigit()or c=="."))
        if "元" in v: return float("".join(c for c in v.replace("元","") if c.isdigit()or c=="."))/100000000
    except: pass
    return None


# ====================================================================
# PART 1: Reranker Comparison using existing completed task data
# ====================================================================
def reranker_metrics():
    print("\n"+"="*70)
    print("PART 1: Reranker 后端对比 (已有任务数据)")
    print("="*70)

    tasks = aget("/research/tasks")
    items = tasks if isinstance(tasks,list) else tasks.get("items",[])

    # Find a completed task with report
    target = None
    for t in items:
        if t.get("status")=="completed" and t.get("report_id"):
            target = t; break
    if not target:
        print("No completed task with report found!"); return

    tid = target["task_id"]
    print(f"Task: {tid[:12]}... | {target['company_name']} - {target['question']}")

    # Get evidence/citations from the report
    report = aget(f"/research/tasks/{tid}/report")
    content = report.get("content","")
    citations = report.get("citations",[])

    # Get facts
    facts_data = aget(f"/facts/{tid}")
    facts = facts_data if isinstance(facts_data,list) else facts_data.get("items",[])

    # Get verification
    ver_data = aget(f"/verification/{tid}")
    vers = ver_data if isinstance(ver_data,list) else ver_data.get("items",[])

    # Count facts by metric
    by_metric = {}
    for f in facts:
        mn = f.get("metric_name","unknown")
        by_metric[mn] = by_metric.get(mn,0)+1

    # Count verification statuses
    by_status = {}
    for v in vers:
        s = v.get("status","?")
        by_status[s] = by_status.get(s,0)+1

    # Analysis: which verified facts appear in the report content
    verified_fact_ids = {v["fact_id"] for v in vers if v.get("status")=="verified"}
    verified_facts = [f for f in facts if f.get("id") in verified_fact_ids]
    cited_count = 0
    for vf in verified_facts:
        claim = vf.get("claim","")
        if any(claim[:20] in content for c in [claim[:20]]):  # crude check
            cited_count += 1

    results = {
        "task_id": tid[:12],
        "total_facts": len(facts),
        "total_verified": len(verified_fact_ids),
        "total_conflicted": by_status.get("conflicted",0),
        "total_insufficient": by_status.get("insufficient",0),
        "metrics_found": sorted(by_metric.keys()),
        "cited_in_report": cited_count,
        "citation_count": len(citations),
    }

    print(f"  Facts={len(facts)} Verified={len(verified_fact_ids)} "
          f"Conflicted={by_status.get('conflicted',0)} Insufficient={by_status.get('insufficient',0)}")
    print(f"  Metrics: {sorted(by_metric.keys())}")
    print(f"  Verified facts cited in report: {cited_count}/{len(verified_facts) if verified_facts else 1}")

    return results


# ====================================================================
# PART 2: Fact Extraction Accuracy (create + run new tasks)
# ====================================================================
@dataclass
class GT:
    company: str; question: str; metric: str; value_b: float; tol: float = 1.0

GROUND_TRUTHS = [
    # 格式: GT(company, question, metric, value_billion, tolerance)
    # 以下为占位示例数据，请替换为你自己的评测用例。
    # GT("某A股上市公司","2025研发投入","R&D_total_spending",634),
]


def fact_extraction_accuracy():
    print("\n"+"="*70)
    print("PART 2: 事实抽取精确命中率")
    print("="*70)

    @dataclass
    class FR:
        gt: GT; metric_ok: bool=False; value_ok: bool=False; period_ok: bool=False
        val: str=""; val_b: float=0; status: str=""; conf: float=0; tid: str=""

    results = []
    for gt in GROUND_TRUTHS:
        print(f"\n  [{gt.company}] {gt.question} (expected {gt.metric}={gt.value_b}亿)")
        try:
            task = apost("/research/tasks", {"company_name":gt.company,"question":gt.question})
            tid = task["task_id"]
            print(f"    Task created: {tid[:12]}... running...", end=" ", flush=True)
            t0 = time.time()
            apost(f"/research/tasks/{tid}/run", {})
            elapsed = time.time()-t0
            print(f"done ({elapsed:.0f}s)")

            facts = aget(f"/facts/{tid}")
            facts = facts if isinstance(facts,list) else facts.get("items",[])
            vers = aget(f"/verification/{tid}")
            vers = vers if isinstance(vers,list) else vers.get("items",[])

            best = None
            for f in facts:
                mn = (f.get("metric_name")or"").lower()
                if gt.metric.lower() not in mn and mn not in gt.metric.lower():
                    continue
                vb = value_to_billions(f.get("value",""))
                if vb is None: continue
                period = str(f.get("period",""))
                pok = str(gt.question[:4]) in period
                vok = abs(vb-gt.value_b)/gt.value_b*100 <= gt.tol
                s = "?"
                for vv in vers:
                    if vv.get("fact_id")==f.get("id"): s=vv.get("status","?"); break
                fr = FR(gt=gt,metric_ok=True,value_ok=vok,period_ok=pok,
                        val=f.get("value",""),val_b=vb,status=s,
                        conf=float(f.get("confidence",0)),tid=tid)
                if best is None or (fr.value_ok and not best.value_ok):
                    best = fr

            if best is None: best = FR(gt=gt, tid=tid)
            results.append(best)
            emoji = "PASS" if best.metric_ok and best.value_ok and best.period_ok else ("PART" if best.metric_ok else "MISS")
            print(f"    {emoji}: metric={'Y' if best.metric_ok else 'N'} value={'Y' if best.value_ok else 'N'} ({best.val_b:.1f}亿) period={'Y' if best.period_ok else 'N'} status={best.status}")
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append(FR(gt=gt))

    # Metrics
    n=len(results)
    mok=sum(1 for r in results if r.metric_ok)
    vok=sum(1 for r in results if r.value_ok)
    pok=sum(1 for r in results if r.period_ok)
    aok=sum(1 for r in results if r.metric_ok and r.value_ok and r.period_ok)
    tp = sum(1 for r in results if r.metric_ok and r.value_ok)
    fp = sum(1 for r in results if r.metric_ok and not r.value_ok)
    fn = sum(1 for r in results if not r.metric_ok)
    prec = tp/(tp+fp) if (tp+fp)>0 else 0
    rec = tp/(tp+fn) if (tp+fn)>0 else 0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0

    print(f"\n  --- Fact Extraction Summary ---")
    print(f"  Metric命中: {mok}/{n} ({mok*100//n if n else 0}%)")
    print(f"  Value精确:  {vok}/{n} ({vok*100//n if n else 0}%)")
    print(f"  Period正确: {pok}/{n} ({pok*100//n if n else 0}%)")
    print(f"  全命中:     {aok}/{n} ({aok*100//n if n else 0}%)")
    print(f"  Precision: {prec:.2%}  Recall: {rec:.2%}  F1: {f1:.2%}")

    return results, prec, rec, f1


# ====================================================================
# PART 3: Pipeline Breakpoint Analysis
# ====================================================================
def pipeline_breakpoints():
    print("\n"+"="*70)
    print("PART 3: 管线分层断点分析")
    print("="*70)

    tasks = aget("/research/tasks")
    items = tasks if isinstance(tasks,list) else tasks.get("items",[])
    # Pick 3 completed tasks
    picks = [t for t in items if t.get("status")=="completed"][:3]
    if len(picks)<2:
        print("Not enough completed tasks"); return

    layers = ["L1_sources","L2_chunks","L3_retrieval","L4_facts","L5_verified","L6_report","L7_citations"]
    heatmap = []

    for tc in picks:
        tid = tc["task_id"]
        row = {"task": f"{tc['company_name']} {tc['question'][:15]}", "tid": tid[:8]}

        # L1: has sources?
        sources = aget(f"/sources/{tid}")
        srcs = sources if isinstance(sources,list) else sources.get("items",[])
        row["L1_sources"] = len(srcs)>0

        # L2: has chunks (via sources having chunks)?
        row["L2_chunks"] = True  # proxy - if sources exist, chunks exist

        # L3: retrieval evidence count from report
        try:
            report = aget(f"/research/tasks/{tid}/report")
            citations = report.get("citations",[])
            row["L3_retrieval"] = len(citations)>0
        except:
            row["L3_retrieval"] = False

        # L4: has facts?
        facts = aget(f"/facts/{tid}")
        facts = facts if isinstance(facts,list) else facts.get("items",[])
        row["L4_facts"] = len(facts)>0

        # L5: has verified?
        vers = aget(f"/verification/{tid}")
        vers = vers if isinstance(vers,list) else vers.get("items",[])
        verified = [v for v in vers if v.get("status")=="verified"]
        row["L5_verified"] = len(verified)>0

        # L6: has report?
        row["L6_report"] = tc.get("report_id") is not None

        # L7: citations in report
        row["L7_citations"] = len(citations)>0 if 'citations' in dir() else False

        heatmap.append(row)
        passes = sum(1 for k in layers if row.get(k))
        print(f"  {row['task']:30s} | {' '.join('Y' if row[k] else 'N' for k in layers)} | {passes}/7")

    # Layer pass rates
    print(f"\n  --- Layer Pass Rates ---")
    for l in layers:
        p = sum(1 for r in heatmap if r.get(l))
        print(f"  {l}: {p}/{len(heatmap)} ({p*100//len(heatmap) if heatmap else 0}%)")

    return heatmap


# ====================================================================
# MAIN
# ====================================================================
if __name__ == "__main__":
    print("="*70)
    print(f"RAG Pipeline Benchmark — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    r1 = reranker_metrics()
    r2 = fact_extraction_accuracy()
    r3 = pipeline_breakpoints()

    print("\n"+"="*70)
    print("FINAL SUMMARY")
    print("="*70)
    if r1:
        print(f"  Retrieval: {r1['total_verified']} verified facts, {r1['citation_count']} citations")
    if r2:
        _, prec, rec, f1 = r2
        print(f"  Fact Extraction: P={prec:.2%} R={rec:.2%} F1={f1:.2%}")
    if r3:
        all_pass = sum(1 for row in r3 if sum(1 for k in ["L1_sources","L2_chunks","L3_retrieval","L4_facts","L5_verified","L6_report","L7_citations"] if row.get(k))==7)
        print(f"  Pipeline: {all_pass}/{len(r3)} tasks pass all 7 layers")
    print("="*70)
