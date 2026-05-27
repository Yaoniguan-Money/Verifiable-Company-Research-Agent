"""DeepSeek OpenAI-compatible chat provider。

只承担局部文本生成（事实抽取的 LLM 兜底、风险分析文本、检索改写、追问回答）。
事实校验、报告骨架、证据链、合规判定都由本地工程链路控制，模型只是文本生成器。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.observability.langfuse_client import maybe_observe
from app.providers.llm.base import LLMProvider
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate, ReportRead
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerContext
from app.services.followup_answer import FollowupPayload
from app.services.followup_prompt import build_followup_llm_prompt
from app.services.report_reader_text import (
    RISK_ANALYSIS_OUTPUT_RULES,
    extract_report_section,
    fact_status_suffix_for_reader,
)
from app.services.report_renderer import MockReportRenderer, ReportRenderInput

# 所有 chat 请求共享的 system prompt（"非投资建议"边界声明）。
_SYSTEM_PROMPT = "你是审慎的企业公开信息研究助手，必须遵守非投资建议边界。"
# Fact 抽取阶段最多取前 N 个 chunk 输入模型，避免上下文超限。
_MAX_FACT_CHUNKS = 8
_CHUNK_TEXT_LIMIT = 1200
# Risk / followup 都展示前 N 条事实摘要，多了 prompt 噪音。
_MAX_FACT_LINES_FOR_RISK = 12


class DeepSeekLLMProvider(LLMProvider):
    """DeepSeek OpenAI-compatible chat provider。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    # ---------- 业务能力 ----------
    def extract_facts(
        self,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        if not chunks:
            return []

        chunk_lines = [
            "\n".join(
                [
                    f"chunk_index={chunk.chunk_index}",
                    f"source_id={chunk.source_id}",
                    f"chunk_id={chunk.id}",
                    f"text={self._truncate(chunk.text, _CHUNK_TEXT_LIMIT)}",
                ]
            )
            for chunk in chunks[:_MAX_FACT_CHUNKS]
        ]
        prompt = "\n\n".join(
            [
                "请从给定公开资料片段中抽取与研究问题直接相关的结构化事实。",

                # --- metric_name 标准化映射 ---
                "metric_name 必须使用以下标准名称之一（括号内为中文含义，请根据片段中的实际措辞选择最准确的）：",
                "  net_profit_parent  （归母净利润 / 归属于上市公司股东的净利润 / 归属于母公司股东的净利润）",
                "  net_profit          （净利润）",
                "  net_profit_deducted （扣非净利润 / 扣除非经常性损益后的净利润）",
                "  R&D_expenditure     （研发费用，利润表中的费用化研发支出）",
                "  R&D_total_spending  （研发投入合计，含资本化的研发总投入）",
                "  revenue             （营业收入 / 营业总收入，合并口径）",
                "  production_capacity （产能）",
                "  production_volume   （产量）",
                "  sales_volume        （销量）",
                "如果片段中的措辞无法匹配以上任一标准名称，请勿抽取该事实。",

                # --- period 格式 ---
                "period 必须只包含四位阿拉伯数字年份（如 2025、2024），不要加「年」「年度」「上半年度」等后缀，不要用中文数字。",

                # --- value 格式 ---
                "value 必须是片段中的原始数值加单位（如 70414214千元、634亿元、22.5GWh），不要四舍五入、不要加「约」「大约」「左右」等模糊词。",

                # --- 禁止行为 ---
                "禁止：对多个数值做算术运算（如加减乘除、翻倍推算全年）。",
                "禁止：抽取增减幅、增长率、百分比变化作为绝对指标值。",
                "禁止：编造 source_id 或 chunk_id，必须从输入中严格照抄。",
                "禁止：抽取「较上年增长 X%」「同比上升 Y%」等相对变化描述。",

                "只能返回严格 JSON，不要输出 Markdown、解释或自然语言前后缀。",
                "JSON 格式必须是：",
                '{"facts":[{"claim":"...","metric_name":"...","value":"...","period":"...","source_id":"...","chunk_id":"...","confidence":0.0}]}',
                "要求：claim 必须来自片段内容；confidence 固定填 1.0 即可（系统会自行校正）。",
                "如果片段没有足够证据支撑事实，请返回 {\"facts\":[]}。",
                f"task_id={task_id}",
                f"company_name={company_name}",
                f"question={question}",
                "资料片段：",
                *chunk_lines,
            ]
        )
        text = self._chat(prompt, max_tokens=1200)
        return self._parse_extracted_facts(text, task_id=task_id, chunks=chunks)

    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        prompt = self._build_risk_prompt(
            company_name=company_name,
            question=question,
            facts=facts,
            verification_results=verification_results,
            include_date_hint=True,
        )
        return self._chat(prompt, max_tokens=700)

    def analyze_risks_streaming(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
        *,
        on_token: Callable[[str], None],
    ) -> str:
        prompt = self._build_risk_prompt(
            company_name=company_name,
            question=question,
            facts=facts,
            verification_results=verification_results,
            include_date_hint=False,
        )
        return self._chat(prompt, max_tokens=700, stream=True, on_token=on_token)

    def generate_report(
        self,
        task: ResearchTaskRead,
        verified_facts: list[ExtractedFactRead],
        conflicted_facts: list[ExtractedFactRead],
        insufficient_facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
        risk_analysis: str,
        citations: list[Citation],
        outdated_facts: list[ExtractedFactRead] | None = None,
        rejected_facts: list[ExtractedFactRead] | None = None,
        core_facts: list[ExtractedFactRead] | None = None,
        supporting_facts: list[ExtractedFactRead] | None = None,
        relevance_intents: list[str] | None = None,
        reader_summary: str | None = None,
        answer_context: AnswerContext | None = None,
    ) -> ReportCreate:
        # 报告结构依然由本地 renderer 控制；DeepSeek 只是负责标题/口径替换。
        report = MockReportRenderer().render(
            ReportRenderInput(
                task=task,
                core_facts=core_facts or [],
                supporting_facts=supporting_facts or [],
                relevance_intents=relevance_intents or [],
                verified_facts=verified_facts,
                conflicted_facts=conflicted_facts,
                insufficient_facts=insufficient_facts,
                verification_results=verification_results,
                risk_analysis=risk_analysis,
                citations=citations,
                outdated_facts=outdated_facts or [],
                rejected_facts=rejected_facts or [],
                reader_summary=reader_summary,
                answer_context=answer_context,
            )
        )
        return report.model_copy(
            update={
                "title": report.title.replace("（Mock）", "（DeepSeek 辅助生成）"),
                "content": report.content.replace("（Mock）", "（DeepSeek 辅助生成）"),
            }
        )

    def answer_followup(
        self,
        *,
        task: ResearchTaskRead,
        message: str,
        report: ReportRead,
        fact_count: int,
        verification_counts: dict[str, int],
        followup_payload: FollowupPayload | None = None,
    ) -> str:
        prompt = build_followup_llm_prompt(
            task=task,
            message=message,
            report=report,
            followup_payload=followup_payload,
        )
        return self._chat(prompt, max_tokens=800)

    def rewrite_retrieval_query(self, question: str) -> str:
        prompt = (
            "将下列企业研究问题改写为更适合检索年报、公告与官方披露的关键词句。"
            "只返回一句中文，不要解释、不要 Markdown。\n"
            f"问题：{question.strip()}"
        )
        return self._chat(prompt, max_tokens=120).strip()

    def infer_research_time_scope(self, question: str) -> dict[str, object] | None:
        from app.services.question_time_scope import parse_llm_time_scope_json

        prompt = (
            "分析下列企业研究问题的时间范围意图，只返回 JSON，不要解释。\n"
            "字段：\n"
            '- window_years: 整数或 null（如「近一年」→1，「近三年」→3，未提及→null）\n'
            '- explicit_years: 整数数组（问题中出现的年份，如 [2024]）\n'
            '- strict: 布尔（仅当用户明确「仅/只要/仅限/只看」某期间时为 true）\n'
            f"问题：{question.strip()}"
        )
        text = self._chat(prompt, max_tokens=120).strip()
        return parse_llm_time_scope_json(text)

    # ---------- prompt 构造 ----------
    def _build_risk_prompt(
        self,
        *,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
        include_date_hint: bool,
    ) -> str:
        fact_lines: list[str] = []
        for item in facts[:_MAX_FACT_LINES_FOR_RISK]:
            status = self._status_for_fact(item, verification_results)
            label = fact_status_suffix_for_reader(status)
            suffix = f"（{label}）" if label else ""
            fact_lines.append(f"- {item.claim}{suffix}")
        if not fact_lines:
            fact_lines = ["- 当前没有可引用的结构化事实。"]
        lines = [
            "你是企业公开信息研究助手，只能基于下列事实写「风险观察」小节。",
            "禁止输出买入/卖出/目标价/收益承诺/个性化投资建议。",
        ]
        if include_date_hint:
            # 避免模型把已披露的年份当作"未来期间"。
            lines.append(
                f"当前日期：{datetime.now(timezone.utc).date().isoformat()}。"
                "不要把早于或等于当前年份的披露期间误判为未来期间。"
            )
        lines.extend(
            [
                f"企业：{company_name}",
                f"研究问题：{question}",
                "事实与核对情况：",
                *fact_lines,
                RISK_ANALYSIS_OUTPUT_RULES,
            ]
        )
        return "\n".join(lines)

    # ---------- HTTP 调用 ----------
    @maybe_observe(name="deepseek_chat")
    def _chat(
        self,
        prompt: str,
        *,
        max_tokens: int,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """统一 chat 入口：流式与同步共享同一份 payload 与错误处理。"""
        if stream and on_token is None:
            raise ValueError("stream=True 时必须传入 on_token")

        payload = self._build_chat_payload(prompt=prompt, max_tokens=max_tokens, stream=stream)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        if stream:
            return self._stream_chat(url=url, headers=headers, payload=payload, on_token=on_token)  # type: ignore[arg-type]
        return self._sync_chat(url=url, headers=headers, payload=payload)

    def _build_chat_payload(self, *, prompt: str, max_tokens: int, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _sync_chat(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> str:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError("DeepSeek API request failed") from exc
        return self._extract_chat_content(data)

    def _stream_chat(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        on_token: Callable[[str], None],
    ) -> str:
        parts: list[str] = []
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    for delta in self._iter_stream_deltas(response.iter_lines()):
                        parts.append(delta)
                        on_token(delta)
        except httpx.HTTPError as exc:
            raise RuntimeError("DeepSeek streaming request failed") from exc
        return "".join(parts).strip()

    @staticmethod
    def _iter_stream_deltas(lines: Iterable[str]) -> Iterable[str]:
        """解析 OpenAI 风格的 SSE 流，按行 yield 出 token 增量。"""
        for line in lines:
            if not line or not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield str(delta)

    @staticmethod
    def _extract_chat_content(data: dict[str, Any]) -> str:
        try:
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("DeepSeek API returned an unexpected response shape") from exc
        text = str(content).strip()
        if text:
            return text
        # 处理 ``reasoning_content`` 但 ``content`` 为空的情况（多见于推理型模型截断）。
        reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
        finish = choice.get("finish_reason") if isinstance(choice, dict) else None
        if str(reasoning or "").strip() and finish == "length":
            raise RuntimeError(
                "DeepSeek returned reasoning_content but no final message.content; "
                "use deepseek-chat for smoke tests or increase max_tokens."
            )
        raise RuntimeError("DeepSeek API returned an empty response")

    # ---------- 解析与工具 ----------
    @staticmethod
    def _status_for_fact(
        fact: ExtractedFactRead,
        verification_results: list[VerificationResultRead],
    ) -> str:
        for item in verification_results:
            if item.fact_id == fact.id:
                return str(item.status)
        return "unknown"

    def _parse_extracted_facts(
        self,
        text: str,
        *,
        task_id: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        # 模型偶尔把 JSON 包在 ```json``` fence 里，先剥离再 parse。
        raw_text = text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`").removeprefix("json").strip()
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, dict) or not isinstance(raw.get("facts"), list):
            return []

        # 限定 (source_id, chunk_id) 只允许使用输入里给出的，杜绝模型杜撰来源。
        allowed_pairs = {(chunk.source_id, chunk.id) for chunk in chunks}
        facts: list[ExtractedFactCreate] = []
        seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
        for item in raw["facts"]:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", "")).strip()
            chunk_id = str(item.get("chunk_id", "")).strip()
            if (source_id, chunk_id) not in allowed_pairs:
                continue
            try:
                metric_name = _normalize_llm_metric_name(item.get("metric_name"))
                period = _normalize_llm_period(item.get("period"))
                fact = ExtractedFactCreate(
                    task_id=task_id,
                    claim=str(item.get("claim", "")).strip(),
                    metric_name=metric_name,
                    value=item.get("value"),
                    period=period,
                    source_id=source_id,
                    chunk_id=chunk_id,
                    confidence=1.0,  # LLM facts always bypass regex cross-source check
                )
            except (TypeError, ValueError, ValidationError):
                continue
            key = (fact.source_id, fact.chunk_id, fact.metric_name, fact.period, fact.value)
            if key in seen:
                continue
            seen.add(key)
            facts.append(fact)
        return facts

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        normalized = text.strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."


def _normalize_llm_period(period: object) -> str | None:
    """Normalize LLM period output: strip 年度/年 suffix, keep only 4-digit year."""
    if period is None:
        return None
    raw = str(period).strip()
    # "2025年度" / "2025年" / "二零二五年" → "2025"
    m = __import__("re").search(r"(20\d{2})", raw)
    if m:
        return m.group(1)
    # Chinese numerals → digit (basic: 二零二五 → 2025)
    _cn = {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
           "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    translated = "".join(_cn.get(ch, ch) for ch in raw)
    m2 = __import__("re").search(r"(20\d{2})", translated)
    return m2.group(1) if m2 else raw


_LLM_METRIC_MAP = {
    "归母净利润": "net_profit_parent",
    "归属于上市公司股东的净利润": "net_profit_parent",
    "归属于母公司股东的净利润": "net_profit_parent",
    "归属于母公司所有者的净利润": "net_profit_parent",
    "净利润": "net_profit",
    "扣非净利润": "net_profit_deducted",
    "扣除非经常性损益后的净利润": "net_profit_deducted",
    "扣除非经常性损益的净利润": "net_profit_deducted",
    "研发费用": "R&D_expenditure",
    "研发投入": "R&D_total_spending",
    "研发投入合计": "R&D_total_spending",
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "营收": "revenue",
    "产能": "production_capacity",
    "产量": "production_volume",
    "销量": "sales_volume",
}


def _normalize_llm_metric_name(raw: object) -> str | None:
    """Map Chinese metric names from LLM output to standard English names."""
    if raw is None:
        return None
    key = str(raw).strip()
    if key in _LLM_METRIC_MAP:
        return _LLM_METRIC_MAP[key]
    # If already an English standard name, keep it
    if key in _LLM_METRIC_MAP.values():
        return key
    # Unknown metric — keep as-is (may fail downstream, but don't silently drop)
    return key
