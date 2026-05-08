"""Report grounding and citation assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chunk import Citation
from app.schemas.common import (
    SOURCE_CREDIBILITY_SCORE_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    SOURCE_METADATA_KEY,
    source_layer_priority,
)
from app.schemas.retrieval import RetrievedEvidence

FORBIDDEN_TERMS = [
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "目标价",
    "收益承诺",
    "个股推荐",
    "适合你购买",
]


@dataclass(frozen=True, slots=True)
class GroundedReportSection:
    """接地后的报告片段。"""

    title: str
    content: str
    citations: list[Citation]


class ReportGroundingService:
    """将 `RetrievedEvidence` 转为可追溯 citation，并生成最小“证据摘要”段落。

    本服务只做 citation 绑定与摘要拼装，不生成最终报告、不做 QA grounding。
    """

    def format_citations(self, evidences: list[RetrievedEvidence]) -> list[Citation]:
        """将检索证据转为 citation，按 (source_id, chunk_id) 去重。"""
        seen: set[tuple[str, str]] = set()
        out: list[Citation] = []
        for ev in evidences:
            key = (ev.source_id, ev.chunk_id)
            if key in seen:
                continue
            out.append(
                Citation(
                    source_id=ev.source_id,
                    chunk_id=ev.chunk_id,
                    url=ev.source_url,
                    title=ev.source_title,
                    retrieved_at=ev.retrieved_at,
                )
            )
            seen.add(key)
        return out

    def build_grounded_section(
        self,
        *,
        query: str,
        evidences: list[RetrievedEvidence],
        max_items: int = 3,
    ) -> GroundedReportSection:
        """构建最小“证据摘要”段落。

        - 有 evidence：输出基于证据片段的摘要要点与 citation。
        - 无 evidence：明确“证据不足”，且 citations 为空。
        """
        q = query.strip()
        if not q:
            raise ValueError("query 不能为空或仅空白")

        if not evidences:
            return GroundedReportSection(
                title="证据摘要（Grounded）",
                content=(
                    f"围绕问题“{q}”，当前检索结果证据不足，暂不形成带来源支持的细化结论。"
                    "建议补充公开资料后再进行下一轮检索。"
                ),
                citations=[],
            )

        ranked = sorted(
            evidences,
            key=lambda ev: (
                source_layer_priority((ev.metadata or {}).get(SOURCE_METADATA_KEY, {}).get(SOURCE_LAYER_METADATA_KEY)),
                float((ev.metadata or {}).get(SOURCE_CREDIBILITY_SCORE_METADATA_KEY) or 0),
                ev.score,
            ),
            reverse=True,
        )
        picked = ranked[: max(1, max_items)]
        lines = [f"围绕问题“{q}”，检索到以下可追溯证据片段：", ""]
        for idx, ev in enumerate(picked, start=1):
            snippet = ev.text.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:80] + "..."
            lines.append(
                f"{idx}. 来源《{ev.source_title}》片段（score={ev.score:.3f}）：{snippet}"
            )
        lines.append("")
        lines.append("注：以上为公开资料证据摘要，不构成投资建议。")

        content = "\n".join(lines)
        lowered = content.lower()
        if any(term.lower() in lowered for term in FORBIDDEN_TERMS):
            raise ValueError("grounded section 命中违规词，请调整模板文案")

        return GroundedReportSection(
            title="证据摘要（Grounded）",
            content=content,
            citations=self.format_citations(picked),
        )
