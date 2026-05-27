"""LLM 追问 prompt 构建（DeepSeek / 千帆共用）。"""

from __future__ import annotations

from app.schemas.report import ReportRead
from app.schemas.task import ResearchTaskRead
from app.services.followup_answer import FollowupPayload
from app.services.report_reader_text import (
    FOLLOWUP_ANSWER_RULES,
    REPORT_SECTION_SUMMARY,
    extract_report_section,
)

FOLLOWUP_REPORT_BRIEF_LIMIT = 1800

_FOLLOWUP_DENY_RULE_ZH = (
    "硬性规则：若 followup_facts_json 不为 [] 或 followup_ambiguities 非空，"
    "不得声称报告缺少或未包含相关数据；须基于这些事实作答，或说明口径歧义。"
)
_FOLLOWUP_DENY_RULE_EN = (
    "Hard rule: if followup_facts_json is not [] or followup_ambiguities is not empty, "
    "do not say the report lacks or does not contain the data. "
    "Answer from these facts or describe the ambiguity."
)


def truncate_followup_text(text: str, limit: int = FOLLOWUP_REPORT_BRIEF_LIMIT) -> str:
    cleaned = text.strip()
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def build_followup_llm_prompt(
    *,
    task: ResearchTaskRead,
    message: str,
    report: ReportRead,
    followup_payload: FollowupPayload | None = None,
    report_brief_limit: int = FOLLOWUP_REPORT_BRIEF_LIMIT,
) -> str:
    """组装追问 user prompt；provider 仅负责调用 chat API。"""
    summary_block = extract_report_section(report.content, REPORT_SECTION_SUMMARY)
    brief_source = summary_block or report.content.strip().replace("\n", " ")
    report_brief = truncate_followup_text(brief_source, report_brief_limit)

    if followup_payload is None:
        primary_facts_json = "[]"
        ambiguities_repr = "[]"
        citation_lines = ""
    else:
        primary_facts_json = followup_payload.primary_facts_json
        ambiguities_repr = str(followup_payload.ambiguities)
        citation_lines = "\n".join(followup_payload.citation_lines)

    return "\n".join(
        [
            "你是企业公开信息研究助手。回答必须严格基于下列报告与结构化事实，"
            "不得补充报告外常识或未经引用的信息。",
            "禁止买入、卖出、加仓、减仓、目标价、收益承诺、个股推荐、个性化投资建议。",
            f"企业：{task.company_name}",
            f"用户追问：{message}",
            "报告正文（优先使用「总结」与「核心发现」）：",
            report_brief,
            "followup_facts_json:",
            primary_facts_json,
            "followup_ambiguities:",
            ambiguities_repr,
            "followup_citations:",
            citation_lines,
            _FOLLOWUP_DENY_RULE_ZH,
            _FOLLOWUP_DENY_RULE_EN,
            FOLLOWUP_ANSWER_RULES,
        ]
    )
