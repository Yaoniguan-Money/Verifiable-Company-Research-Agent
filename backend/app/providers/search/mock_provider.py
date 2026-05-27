"""MockSearchProvider：阶段 1 的公开信息来源占位实现。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.providers.search.base import SearchProvider
from app.schemas.common import SourceType
from app.schemas.source import SourceCreate


class MockSearchProvider(SearchProvider):
    """Return unmistakable mock sources for local smoke tests.

    These records must never look like real search results. Earlier versions
    used plausible report/news titles and example.com URLs, which made local
    smoke-test output easy to misread as live web search.
    """

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        now = datetime.now(timezone.utc)
        placeholder_task_id = "TBD_BY_WORKFLOW"
        mock_notice = (
            "MOCK_PROVIDER_ONLY：这是本地开发占位数据，不是联网搜索结果，"
            "不代表任何真实公司、公告、年报或新闻。"
        )
        return [
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"[MOCK 演示占位] {company_name} - 非真实年度报告",
                url=f"mock://local/{company_name}/placeholder-annual-report",
                source_type=SourceType.OTHER,
                published_at=datetime(2024, 4, 25, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"{mock_notice} 用户输入公司：{company_name}。"
                    f"用户输入问题：{question}。"
                    "MOCK演示指标：2024年营收为100亿元，2024年净利润为10亿元，2024年研发投入为5亿元；"
                    "这些数值只用于本地流程测试，不是事实。"
                    "如需真实公开资料，请配置 SEARCH_PROVIDER=baidu_ai_search、"
                    "SEARCH_PROVIDER=cninfo_announcements 或 SEARCH_PROVIDER=public_sources。"
                ),
                credibility_score=0.61,
                source_metadata={"provider": "mock", "mock": True},
            ),
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"[MOCK 演示占位] {company_name} - 非真实公告",
                url=f"mock://local/{company_name}/placeholder-announcement",
                source_type=SourceType.OTHER,
                published_at=datetime(2024, 8, 2, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"{mock_notice} 这条记录只用于验证 workflow 是否能落库、切分、"
                    "抽取和渲染报告；不得作为事实依据。"
                    "MOCK演示指标：2024年营收为120亿元，2024年净利润为8亿元。"
                ),
                credibility_score=0.61,
                source_metadata={"provider": "mock", "mock": True},
            ),
            SourceCreate(
                task_id=placeholder_task_id,
                title=f"[MOCK 演示占位] {company_name} - 非真实新闻",
                url=f"mock://local/{company_name}/placeholder-news",
                source_type=SourceType.OTHER,
                published_at=datetime(2025, 1, 10, tzinfo=timezone.utc),
                retrieved_at=now,
                raw_content=(
                    f"{mock_notice} 当前配置不会访问互联网，也不会校验 {company_name} "
                    "的真实公开披露。MOCK演示指标：2024年研发投入为5亿元。"
                ),
                credibility_score=0.61,
                source_metadata={"provider": "mock", "mock": True},
            ),
        ]
