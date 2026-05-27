import sys, math, time, os
sys.path.insert(0, '/app/backend')
os.environ['HF_ENDPOINT'] = os.getenv('HF_ENDPOINT', 'https://huggingface.co')
from app.services.rag.reranker import OnnxReranker

CHUNKS = [
    ('研发费用 22,146,581 18,606,756 19.02%',1),('研发投入金额（千元） 22,146,581 18,606,756 18,356,108',1),
    ('研发投入占营业收入比例 5.23% 5.14% 4.58%',1),('公司拥有及申请的国内外专利总数达 54,538 项',1),
    ('依托行业顶尖的研发团队与持续高强度的研发投入',1),('一是研发为核，产品矩阵持续迭代',1),
    ('骁遥双核电池 确保动力输出的连续性与安全性',1),('钠新电池 突破常规锂电体系',1),
    ('超混电池 超越常规体系，实现更高比能、更长寿命',1),
    ('2025年1-6月中国三元与磷酸铁锂正极材料合计产量为192.3万吨',0),
    ('销售费用 3,735,118 3,562,797 4.84%',0),('管理费用 11,666,741 9,689,839 20.40%',0),
    ('财务费用 -7,939,863 -4,131,918 92.16%',0),('前五名供应商合计采购金额 59,938,203',0),
    ('2025年全球新能源车销量为2147.0万辆',0),('公司实现储能电池销量为121GWh',0),
    ('公司实现锂离子电池销量为661GWh',0),('公司境外分业务收入为129641258千元',0),
    ('公司在山东东营市签署战略合作协议',0),('公司宣布量产交付587Ah大容量储能专用电芯',0),
    ('与新蔚来达成战略合作',0),('与中石化全面深化长期战略合作关系',0),
    ('经营活动现金流入小计511868353',0),('所得税费用12740236',0),
    ('资产减值损失-8660164',0),('信用减值损失-418585',0),
    ('会计估计变更长期资产折旧年限由5年变更为3年',0),
]
TEXTS = [c[0] for c in CHUNKS]
REL = {i for i, c in enumerate(CHUNKS) if c[1]}
Q = '某A股新能源上市公司 2025年研发投入'

print('Loading ONNX model...')
t0 = time.time()
r = OnnxReranker()
print(f'Model loaded in {time.time()-t0:.0f}s')
print(f'Chunks={len(TEXTS)} Relevant={len(REL)} Query={Q}\n')

t0 = time.time()
ranks = r.rerank(Q, TEXTS, top_k=30)
lat = (time.time()-t0)*1000
indices = [i for i, _ in ranks]
rel = [1 if i in REL else 0 for i in indices]
TR = len(REL)

for i, (idx, score) in enumerate(ranks[:10]):
    tag = 'R' if idx in REL else '.'
    print(f'  {i+1}. [{tag}] score={score:.4f} | {TEXTS[idx][:80]}')

def pk(k): return sum(rel[:k])/k
def rk(k): return sum(rel[:k])/TR
p5, p10 = pk(5), pk(10)
r5, r10 = rk(5), rk(10)
f1_5 = 2*p5*r5/(p5+r5) if (p5+r5)>0 else 0
f1_10 = 2*p10*r10/(p10+r10) if (p10+r10)>0 else 0
mrr = 0
for i, v in enumerate(rel):
    if v: mrr = 1/(i+1); break
dcg = lambda k: sum((2**v-1)/math.log2(i+2) for i, v in enumerate(rel[:k]))
idcg = lambda k: sum((2**v-1)/math.log2(i+2) for i, v in enumerate(sorted([1]*min(TR,k)+[0]*max(0,k-TR), reverse=True)))
n5 = dcg(5)/idcg(5) if idcg(5)>0 else 0
n10 = dcg(10)/idcg(10) if idcg(10)>0 else 0
ap = h = 0
for i, v in enumerate(rel):
    if v: h += 1; ap += h/(i+1)
mp = ap/TR

print(f'\n{"Metric":12s} {"Value":>8s}')
print(f'{"P@5":12s} {p5:8.4f}')
print(f'{"P@10":12s} {p10:8.4f}')
print(f'{"R@5":12s} {r5:8.4f}')
print(f'{"R@10":12s} {r10:8.4f}')
print(f'{"F1@5":12s} {f1_5:8.4f}')
print(f'{"F1@10":12s} {f1_10:8.4f}')
print(f'{"MRR":12s} {mrr:8.4f}')
print(f'{"NDCG@5":12s} {n5:8.4f}')
print(f'{"NDCG@10":12s} {n10:8.4f}')
print(f'{"MAP":12s} {mp:8.4f}')
print(f'{"Latency":12s} {lat:7.0f}ms')
