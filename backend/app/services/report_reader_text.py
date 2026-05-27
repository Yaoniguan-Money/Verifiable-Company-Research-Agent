"""把模型输出与工程字段整理成面向读者的报告用语。"""

from __future__ import annotations

import re

# 风险分析 prompt 末尾的统一输出约束（DeepSeek / 千帆共用）。
RISK_ANALYSIS_OUTPUT_RULES = """
输出格式（必须严格遵守）：
- 面向最终读者，可直接放入研究报告的「风险观察」小节
- 只输出 3～5 行，每行以「- 」开头，每行不超过 80 个汉字
- 只使用上文「事实与核对情况」中已出现的信息，不得补充年报、行业统计或其他外部数据
- 禁止出现：根据您提供、请注意、INSUFFICIENT、status=、### 标题、**加粗**、编号小节、长篇“无法得出结论”的元说明
- 用简洁中文写经营、披露、数据质量方面的审慎关注点；不要解释系统如何工作
- 不要反复写「待核实」「证据不足」等套话；上文已标注来源的条目默认读者可自行核对
""".strip()

# 报告 Markdown 二级标题：读者向总结段。
REPORT_SECTION_SUMMARY = "总结"

# 报告追问回答格式（DeepSeek / 千帆 / 兜底模板共用）。
FOLLOWUP_ANSWER_RULES = """
回答格式（必须严格遵守）：
- 用 2～4 段连贯中文直接回答，像研究员向同事口头总结
- 禁止使用「核心发现」「证据缺口」「验证状态」「可追溯来源限制」等小标题或 checklist
- 不要罗列 verified、conflicted、insufficient 等英文状态，也不要堆砌统计条数
- 材料不足时用一两句自然中文说明缺什么期间或指标，不要写成审计/系统说明
- 严格基于当前报告与来源，不得补充报告外常识；禁止投资建议、目标价、买卖建议
""".strip()


def extract_report_section(content: str, heading: str) -> str:
    """从 Markdown 报告中截取指定二级标题下的正文。"""
    marker = f"## {heading}"
    if marker not in content:
        return ""
    tail = content.split(marker, 1)[1]
    section = tail.split("\n## ", 1)[0]
    lines = [line.strip() for line in section.splitlines() if line.strip() and not line.startswith(">")]
    return "\n".join(lines).strip()


_META_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"根据您(的)?(要求|提供)"),
    re.compile(r"请注意"),
    re.compile(r"由于您提供"),
    re.compile(r"INSUFFICIENT|VERIFIED|CONFLICTED", re.IGNORECASE),
    re.compile(r"status\s*=", re.IGNORECASE),
    re.compile(r"以下(是|为).{0,12}(分析|观察)"),
    re.compile(r"无法(得出|形成).{0,8}可靠结论"),
    re.compile(r"建议以.{0,20}(为准|查阅)"),
)

# 模型常擅自补外部年报数值，这类句子不应进入读者正文。
_EXTERNAL_SOURCE_CLAIM = re.compile(
    r"(（来源[：:]|来源[：:][^）]{0,40}年?报|据.{0,8}年?报|巨潮|上交所|港交所)"
)


def verification_status_label(status: str) -> str:
    """校验状态 → 读者可读标签（仅用于冲突/排除等需要警示的场景）。"""
    labels = {
        "verified": "已核对",
        "conflicted": "口径不一致",
        "insufficient": "线索待补证",
        "outdated": "信息偏旧",
        "rejected": "已排除",
    }
    return labels.get(status, "线索待补证")


def fact_status_suffix_for_reader(status: str | None) -> str | None:
    """正文事实行后缀：已核对与单来源官方披露不写免责声明式标签。"""
    if not status or status in {"verified", "insufficient"}:
        return None
    return verification_status_label(status)


def format_risk_analysis_for_report(text: str, *, max_bullets: int = 5) -> list[str]:
    """将 LLM 风险分析整理为短句列表，去掉元叙述与思考过程口吻。"""
    if max_bullets <= 0:
        return []
    if not (text or "").strip():
        return []

    normalized = text.replace("\r\n", "\n").strip()
    candidates: list[str] = []

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"#{1,4}\s+", line):
            line = re.sub(r"^#{1,4}\s+", "", line).strip()
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+[.、．]\s*", "", line)
        line = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", line).strip(" -*\t")
        if len(line) < 12:
            continue
        if _is_meta_risk_line(line):
            continue
        if _EXTERNAL_SOURCE_CLAIM.search(line) and "引用" not in line:
            continue
        for prefix in ("根据您的要求，", "根据您的要求,", "基于当前报告，", "基于当前报告,"):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
        candidates.append(_truncate_sentence(line, 220))

    if not candidates:
        # 兜底：整段压成一句，但仍过滤元叙述。
        fallback = " ".join(normalized.split())
        fallback = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", fallback)
        if fallback and not _is_meta_risk_line(fallback):
            candidates = [_truncate_sentence(fallback, 220)]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item[:48]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_bullets:
            break
    return deduped


def _is_meta_risk_line(text: str) -> bool:
    return any(pattern.search(text) for pattern in _META_LINE_PATTERNS)


def _truncate_sentence(text: str, limit: int) -> str:
    cleaned = text.strip()
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
