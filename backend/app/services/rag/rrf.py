"""倒数排名融合（RRF）。"""

from __future__ import annotations

DEFAULT_RRF_K = 60
DEFAULT_RRF_TOP_N = 30
MIN_RRF_K = 1


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    *,
    k: int = DEFAULT_RRF_K,
    top_n: int = DEFAULT_RRF_TOP_N,
) -> list[str]:
    """合并多路检索排名，返回 chunk_id 列表（分数降序）。"""
    if top_n <= 0:
        return []
    # k 是平滑项，不能让异常配置把分母推到 0 或负数。
    k = max(k, MIN_RRF_K)
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [chunk_id for chunk_id, _ in ordered[:top_n]]
