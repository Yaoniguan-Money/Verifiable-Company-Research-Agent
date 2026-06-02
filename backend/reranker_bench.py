"""Reranker 三后端 A/B 对比 — 直接在容器内跑，绕过 API 直接调检索层。"""
import math
import sys
import time

sys.path.insert(0, "/app/backend")

from app.core.config import Settings
from app.providers.factory import ProviderFactory
from app.services.rag.reranker import EmbeddingReranker, LexicalReranker, OnnxReranker

# ---- 1. Prepare test data ----
CHUNKS_FIXTURE = [
    # Relevant: contain R&D spending data
    ("研发费用 22,146,581 18,606,756 19.02%", True),
    ("研发投入金额（千元） 22,146,581 18,606,756 18,356,108", True),
    ("研发投入占营业收入比例 5.23% 5.14% 4.58%", True),
    ("公司拥有及申请的国内外专利总数达 54,538 项", True),
    ("依托行业顶尖的研发团队与持续高强度的研发投入", True),
    ("具体而言，公司核心竞争力体现在以下方面： 一是研发为核，产品矩阵持续迭代", True),
    ("骁遥双核电池 确保动力输出的连续性与安全性", True),
    ("钠新电池 突破常规锂电体系", True),
    ("超混电池 超越常规体系，实现更高比能、更长寿命", True),
    ("2025年1-6月中国三元与磷酸铁锂正极材料合计产量为192.3万吨", False),
    # Distractors
    ("销售费用 3,735,118 3,562,797 4.84%", False),
    ("管理费用 11,666,741 9,689,839 20.40%", False),
    ("财务费用 -7,939,863 -4,131,918 92.16%", False),
    ("前五名供应商合计采购金额（千元） 59,938,203", False),
    ("公司前 5 名供应商资料 序号 供应商名称 采购额", False),
    ("2025 年全球新能源车销量为 2147.0 万辆", False),
    ("公司实现储能电池销量为 121GWh", False),
    ("公司实现锂离子电池销量为 661GWh", False),
    ("公司境外分业务收入为 129641258 千元", False),
    ("公司在山东东营市、甘肃兰州市等城市签署战略合作协议", False),
    ("公司宣布量产交付 587Ah 大容量储能专用电芯", False),
    ("公司新一代巧克力换电解决方案适配车型广", False),
    ("公司与蔚来达成战略合作以深化乘用车换电网络共享", False),
    ("公司与中石化全面深化长期战略合作关系", False),
    ("经营活动现金流入小计 511,868,353 444,879,417", False),
    ("投资活动现金流入小计 8,303,785", False),
    ("所得税费用 12,740,236 9,175,245", False),
    ("资产减值损失 -8,660,164 -8,423,325", False),
    ("信用减值损失 -418,585 -872,526", False),
    ("会计估计变更 长期资产折旧/摊销年限由5年变更为3年", False),
]

ALL_CHUNKS = [text for text, _ in CHUNKS_FIXTURE]
RELEVANT = {i for i, (_, rel) in enumerate(CHUNKS_FIXTURE) if rel}
QUERY = "某A股新能源上市公司 2025年研发投入"


def compute_metrics(ranked_indices):
    relevance = [1 if i in RELEVANT else 0 for i in ranked_indices]
    total_rel = len(RELEVANT)
    def p_at_k(k): return sum(relevance[:k])/k
    def r_at_k(k): return sum(relevance[:k])/total_rel
    p5, p10 = p_at_k(5), p_at_k(10)
    r5, r10 = r_at_k(5), r_at_k(10)
    f1_5 = 2*p5*r5/(p5+r5) if (p5+r5)>0 else 0
    f1_10 = 2*p10*r10/(p10+r10) if (p10+r10)>0 else 0
    mrr = 0
    for i, rel in enumerate(relevance):
        if rel == 1: mrr = 1.0/(i+1); break
    def dcg(k):
        return sum((2**rel-1)/math.log2(i+2) for i, rel in enumerate(relevance[:k]))
    def idcg(k):
        ideal = sorted([1]*min(total_rel,k)+[0]*max(0,k-total_rel), reverse=True)
        return sum((2**r-1)/math.log2(i+2) for i, r in enumerate(ideal))
    ndcg5 = dcg(5)/idcg(5) if idcg(5)>0 else 0
    ndcg10 = dcg(10)/idcg(10) if idcg(10)>0 else 0
    ap = 0; hits = 0
    for i, rel in enumerate(relevance):
        if rel == 1: hits += 1; ap += hits/(i+1)
    map_score = ap/total_rel
    return {"P@5":round(p5,4),"P@10":round(p10,4),"R@5":round(r5,4),"R@10":round(r10,4),
            "F1@5":round(f1_5,4),"F1@10":round(f1_10,4),"MRR":round(mrr,4),
            "NDCG@5":round(ndcg5,4),"NDCG@10":round(ndcg10,4),"MAP":round(map_score,4)}


def run_one(name, reranker):
    print(f"\n[{name}] ...")
    t0 = time.time()
    ranks = reranker.rerank(QUERY, ALL_CHUNKS, top_k=30)
    lat = (time.time()-t0)*1000
    indices = [i for i, _ in ranks]
    m = compute_metrics(indices)
    m["latency_ms"] = round(lat, 1)
    m["backend"] = name
    for rank, (idx, score) in enumerate(ranks[:5]):
        label = "R" if idx in RELEVANT else "."
        print(f"  {rank+1}. [{label}] score={score:.3f} | {ALL_CHUNKS[idx][:70]}")
    return m


print("=" * 80)
print(f"Reranker 三后端对比 | Chunks={len(ALL_CHUNKS)} (R={len(RELEVANT)}) | Query: {QUERY}")
print("=" * 80)

results = {}

# Lexical
results["lexical"] = run_one("lexical", LexicalReranker())

# Embedding
factory = ProviderFactory(Settings())
emb_provider = factory.create_embedding_provider()
results["embedding"] = run_one("embedding", EmbeddingReranker(emb_provider))

# ONNX
try:
    results["onnx"] = run_one("onnx", OnnxReranker())
except Exception as e:
    print(f"\n[onnx] ERROR: {e}")
    results["onnx"] = {"backend":"onnx","error":str(e)}

# Table
print("\n" + "=" * 100)
metrics = ["P@5","P@10","R@5","R@10","F1@5","F1@10","MRR","NDCG@5","NDCG@10","MAP","latency_ms"]
hdr = f"{'Backend':12s}" + "".join(f"{m:>8s}" for m in metrics)
print(hdr); print("-"*len(hdr))
for b in ["lexical","embedding","onnx"]:
    m = results.get(b,{})
    if "error" in m:
        print(f"{b:12s} ERROR: {m['error']}")
    else:
        vals = "".join(f"{m.get(k,0):8.4f}" if k!="latency_ms" else f"{m.get(k,0):7.0f}ms" for k in metrics)
        print(f"{b:12s}{vals}")
print("=" * 100)
