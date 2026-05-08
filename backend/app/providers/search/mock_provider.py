"""MockSearchProvider：阶段 1 的公开信息来源占位实现。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.providers.search.base import SearchProvider
from app.schemas.common import SourceType
from app.schemas.source import SourceCreate


class MockSearchProvider(SearchProvider):
    """返回企业公开资料风格的 mock 来源。"""

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        now = datetime.now(timezone.utc)
        # 注意：task_id 由 workflow 在落库前填充，这里先放占位值。
        placeholder_task_id = "TBD_BY_WORKFLOW"
        return [
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"{company_name} 2023 年度报告（研发与经营摘要）",
                url=f"https://example.com/{company_name}/annual-report-2023",
                source_type=SourceType.ANNUAL_REPORT,
                published_at=datetime(2024, 4, 25, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"{company_name} 在 2023 年公开披露研发投入持续增长，"
                    "重点投向电池技术与智能制造。报告同时提到原材料成本波动"
                    "和海外业务扩张带来的经营不确定性。"
                    "2023年研发投入为100亿元。2022年营收为500亿元。2023年净利润为20亿元。"
                ),
                credibility_score=0.90,
            ),
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"{company_name} 董事会公告（产能与供应链说明）",
                url=f"https://example.com/{company_name}/announcement-supply-chain",
                source_type=SourceType.ANNOUNCEMENT,
                published_at=datetime(2024, 8, 2, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"{company_name} 公告披露：核心产线扩建项目进入调试期，"
                    "供应链优化已覆盖关键零部件。公告同时提示海外物流成本"
                    "与地缘因素可能影响交付节奏。"
                    "2023年研发投入为100亿元。2022年营收为500亿元。"
                ),
                credibility_score=0.86,
            ),
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"媒体报道：{company_name} 技术投入与市场竞争观察",
                url=f"https://example.com/news/{company_name}-r-and-d-observation",
                source_type=SourceType.NEWS,
                published_at=datetime(2025, 1, 10, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"公开新闻显示，{company_name} 持续增加研发团队规模，"
                    "并在多个细分技术方向发布新进展。分析同时指出行业价格竞争"
                    "与需求波动是未来需要持续跟踪的风险点。"
                    "2022年营收为520亿元。"
                ),
                credibility_score=0.72,
            ),
        ]
