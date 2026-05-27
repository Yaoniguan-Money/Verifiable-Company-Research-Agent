"""百度千帆 chat completions provider。

只接入 LLM 局部能力；搜索、embedding、vector store 和本地合规规则保持现有工程边界。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

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
from app.services.report_renderer import ReportDocumentRenderer, ReportRenderInput

# 与 DeepSeek 一致的"非投资建议"边界声明。
_SYSTEM_PROMPT = "你是审慎的企业公开信息研究助手，必须遵守非投资建议边界。"
_FACT_SYSTEM_PROMPT = "你是企业公开资料事实抽取器，只返回机器可解析的严格 JSON。"
_REPORT_SYSTEM_PROMPT = "你是企业公开信息研究报告撰写助手，只能基于用户提供的证据写作。"

_MAX_FACT_CHUNKS = 8
_CHUNK_TEXT_LIMIT = 1200
_MAX_FACT_LINES_FOR_RISK = 12


def _truncate(text: str, limit: int) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


def _status_for_fact(
    fact: ExtractedFactRead,
    verification_results: list[VerificationResultRead],
) -> str:
    for item in verification_results:
        if item.fact_id == fact.id:
            return str(item.status)
    return "unknown"


class QianfanLLMProvider(LLMProvider):
    """百度千帆 chat completions provider。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://qianfan.baidubce.com/v2",
        model: str = "ernie-4.5-8k-preview",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("QIANFAN_API_KEY is required when LLM_PROVIDER=qianfan")
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
                    f"text={_truncate(chunk.text, _CHUNK_TEXT_LIMIT)}",
                ]
            )
            for chunk in chunks[:_MAX_FACT_CHUNKS]
        ]
        prompt = "\n\n".join(
            [
                "请从给定公开资料片段中抽取与研究问题直接相关的结构化事实。",
                "只能返回严格 JSON，不要输出 Markdown、解释或自然语言前后缀。",
                "JSON 格式必须是：",
                '{"facts":[{"claim":"...","metric_name":"...或null","value":"...或null","period":"...或null","source_id":"...","chunk_id":"...","confidence":0.0}]}',
                "要求：claim 必须来自片段内容；source_id 和 chunk_id 必须使用输入值；confidence 在 0 到 1 之间。",
                f"task_id={task_id}",
                f"company_name={company_name}",
                f"question={question}",
                "资料片段：",
                *chunk_lines,
            ]
        )
        text = self._chat_with_system(_FACT_SYSTEM_PROMPT, prompt, max_tokens=1024)
        return self._parse_extracted_facts(text, task_id=task_id, chunks=chunks)

    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        fact_lines: list[str] = []
        for item in facts[:_MAX_FACT_LINES_FOR_RISK]:
            label = fact_status_suffix_for_reader(_status_for_fact(item, verification_results))
            suffix = f"（{label}）" if label else ""
            fact_lines.append(f"- {item.claim}{suffix}")
        if not fact_lines:
            fact_lines = ["- 当前没有可引用的结构化事实。"]
        prompt = "\n".join(
            [
                "你是企业公开信息研究助手，只能基于下列事实写「风险观察」小节。",
                "禁止输出买入、卖出、目标价、收益承诺、个性化投资建议。",
                f"企业：{company_name}",
                f"研究问题：{question}",
                "事实与核对情况：",
                *fact_lines,
                RISK_ANALYSIS_OUTPUT_RULES,
            ]
        )
        return self._chat_with_system(_SYSTEM_PROMPT, prompt, max_tokens=700)

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
        return ReportDocumentRenderer().render(
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
        ).model_copy(update={"title": f"{task.company_name} 公开信息研究报告（Qianfan 辅助）"})
        summary_hint = (
            f"报告「总结」段必须以此为准（可润色但不得改变数字与结论）：{reader_summary}"
            if reader_summary
            else ""
        )
        prompt = "\n\n".join(
            [
                "请基于给定证据生成中文 Markdown 研究报告，面向普通读者阅读。",
                "硬性要求：不得编造来源、不得补充未给出的事实、不得输出买入/卖出/目标价/收益承诺/个性化投资建议。",
                "如果证据不足或事实冲突，必须明确标注限制，不要强行给结论。",
                "禁止出现：根据您提供、请注意、INSUFFICIENT、status=、系统流程说明、思考过程式长文。",
                "用简洁小节与短句呈现，不要写编号小节或 ### 标题堆砌。",
                f"企业：{task.company_name}",
                f"研究问题：{task.question}",
                f"核心事实：{self._facts_for_prompt(core_facts or [])}",
                f"支持事实：{self._facts_for_prompt(supporting_facts or [])}",
                f"已验证事实：{self._facts_for_prompt(verified_facts)}",
                f"冲突事实：{self._facts_for_prompt(conflicted_facts)}",
                f"证据不足事实：{self._facts_for_prompt(insufficient_facts)}",
                f"过期事实：{self._facts_for_prompt(outdated_facts or [])}",
                f"已拒绝事实：{self._facts_for_prompt(rejected_facts or [])}",
                f"验证结果：{self._verifications_for_prompt(verification_results)}",
                f"引用来源：{self._citations_for_prompt(citations)}",
                f"风险分析：{risk_analysis}",
                f"问题意图：{', '.join(relevance_intents or []) or '未提供'}",
                summary_hint,
            ]
        )
        content = self._chat_with_system(_REPORT_SYSTEM_PROMPT, prompt, max_tokens=1024)
        # 最终输出仍受本地合规判定兜底，确保模型输出不会绕过规则层。
        check = self.check_compliance(content)
        return ReportCreate(
            task_id=task.id,
            title=f"{task.company_name} 公开信息研究报告（Qianfan 辅助生成）",
            content=check.rewritten_text or content,
            citations=citations,
            compliance_status=check.status,
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
        return self._chat_with_system(_SYSTEM_PROMPT, prompt, max_tokens=800)

    # ---------- HTTP ----------
    def _chat_with_system(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> str:
        return self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )

    def _chat(self, messages: list[dict[str, str]], *, max_tokens: int) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError("Qianfan API request failed") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Qianfan API returned an unexpected response shape") from exc
        text = str(content).strip()
        if not text:
            raise RuntimeError("Qianfan API returned an empty response")
        return text

    # ---------- 解析 ----------
    def _parse_extracted_facts(
        self,
        text: str,
        *,
        task_id: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, dict) or not isinstance(raw.get("facts"), list):
            return []

        allowed_pairs = {(chunk.source_id, chunk.id) for chunk in chunks}
        facts: list[ExtractedFactCreate] = []
        for item in raw["facts"]:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", ""))
            chunk_id = str(item.get("chunk_id", ""))
            if (source_id, chunk_id) not in allowed_pairs:
                continue
            try:
                facts.append(
                    ExtractedFactCreate(
                        task_id=task_id,
                        claim=str(item.get("claim", "")).strip(),
                        metric_name=item.get("metric_name"),
                        value=item.get("value"),
                        period=item.get("period"),
                        source_id=source_id,
                        chunk_id=chunk_id,
                        confidence=float(item.get("confidence", 0.5)),
                    )
                )
            except (TypeError, ValueError, ValidationError):
                continue
        return facts

    # ---------- prompt 辅助 ----------
    @staticmethod
    def _facts_for_prompt(facts: list[ExtractedFactRead]) -> str:
        if not facts:
            return "[]"
        return json.dumps(
            [
                {
                    "claim": fact.claim,
                    "metric_name": fact.metric_name,
                    "value": fact.value,
                    "period": fact.period,
                    "source_id": fact.source_id,
                    "chunk_id": fact.chunk_id,
                }
                for fact in facts[:20]
            ],
            ensure_ascii=False,
        )

    @staticmethod
    def _verifications_for_prompt(results: list[VerificationResultRead]) -> str:
        if not results:
            return "[]"
        return json.dumps(
            [
                {
                    "fact_id": item.fact_id,
                    "status": str(item.status),
                    "reason": item.reason,
                    "supporting_sources": item.supporting_sources,
                    "conflicting_sources": item.conflicting_sources,
                }
                for item in results[:30]
            ],
            ensure_ascii=False,
        )

    @staticmethod
    def _citations_for_prompt(citations: list[Citation]) -> str:
        if not citations:
            return "[]"
        return json.dumps(
            [
                {
                    "source_id": item.source_id,
                    "chunk_id": item.chunk_id,
                    "title": item.title,
                    "url": item.url,
                    "retrieved_at": item.retrieved_at.isoformat(),
                }
                for item in citations[:20]
            ],
            ensure_ascii=False,
        )
