from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from app.compliance import ComplianceAction, evaluate_compliance_text
from app.providers.llm.base import ComplianceCheckResult, LLMProvider
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import ComplianceStatus
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate, ReportRead
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from pydantic import ValidationError


class QianfanLLMProvider(LLMProvider):
    """百度千帆 chat completions provider。

    真实模型只接入 LLM 局部能力；搜索、embedding、vector store 和本地合规规则仍保持现有工程边界。
    """

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
                    f"text={self._truncate(chunk.text, 1200)}",
                ]
            )
            for chunk in chunks[:8]
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
        text = self._chat(
            [
                {
                    "role": "system",
                    "content": "你是企业公开资料事实抽取器，只返回机器可解析的严格 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
        )
        return self._parse_extracted_facts(text, task_id=task_id, chunks=chunks)

    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        fact_lines = [
            f"- {item.claim} | status={self._status_for_fact(item, verification_results)}"
            for item in facts[:12]
        ] or ["- 当前没有可用结构化事实。"]
        prompt = "\n".join(
            [
                "你是企业公开信息研究助手，只能基于给定事实做经营、财务、披露和风险分析。",
                "禁止输出买入、卖出、目标价、收益承诺、个性化投资建议。",
                f"企业：{company_name}",
                f"研究问题：{question}",
                "事实与验证状态：",
                *fact_lines,
                "请用中文输出一段审慎的风险观察，必须说明证据不足、冲突或来源限制。",
            ]
        )
        return self._chat(
            [
                {
                    "role": "system",
                    "content": "你是审慎的企业公开信息研究助手，必须遵守非投资建议边界。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
        )

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
    ) -> ReportCreate:
        prompt = "\n\n".join(
            [
                "请基于给定证据生成中文 Markdown 研究报告。",
                "硬性要求：不得编造来源、不得补充未给出的事实、不得输出买入/卖出/目标价/收益承诺/个性化投资建议。",
                "如果证据不足或事实冲突，必须明确标注限制，不要强行给结论。",
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
            ]
        )
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": "你是企业公开信息研究报告撰写助手，只能基于用户提供的证据写作。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
        )
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
    ) -> str:
        report_brief = self._truncate(report.content.strip().replace("\n", " "), 1800)
        prompt = "\n".join(
            [
                "你是企业公开信息研究助手。回答必须严格基于当前报告，不得补充报告外信息。",
                "禁止买入、卖出、加仓、减仓、目标价、收益承诺、个股推荐、个性化投资建议。",
                f"企业：{task.company_name}",
                f"用户追问：{message}",
                f"事实数量：{fact_count}",
                f"验证状态统计：{verification_counts}",
                f"报告摘要：{report_brief}",
                "请用中文回答，并说明依据来自当前报告。",
            ]
        )
        return self._chat(
            [
                {
                    "role": "system",
                    "content": "你是审慎的企业公开信息研究助手，必须遵守非投资建议边界。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
        )

    def check_compliance(self, text: str) -> ComplianceCheckResult:
        # 合规检查必须优先走本地 deterministic rule-based 规则，不能交给远端模型决定。
        decision = evaluate_compliance_text(text)
        violations = [h.matched_snippet for h in decision.hits]
        if decision.action == ComplianceAction.ALLOW:
            return ComplianceCheckResult(
                is_compliant=True,
                status=ComplianceStatus.PASSED,
                violations=[],
                checked_at=datetime.now(timezone.utc),
            )
        if decision.action == ComplianceAction.REWRITE:
            rewritten = text
            for phrase in violations:
                rewritten = rewritten.replace(phrase, "【已移除违规表达】")
            rewritten += "\n\n合规提示：本系统不提供证券投资导向结论。"
            status = ComplianceStatus.REWRITTEN
        else:
            rewritten = (
                "当前请求涉及投资建议或个性化投融导向信息，已按合规策略拒绝。"
                "你可以继续询问企业经营、财务变化、信息披露一致性、供应链稳定性等公开信息问题。"
            )
            status = ComplianceStatus.BLOCKED
        return ComplianceCheckResult(
            is_compliant=False,
            status=status,
            violations=violations,
            rewritten_text=rewritten,
            checked_at=datetime.now(timezone.utc),
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

    def _facts_for_prompt(self, facts: list[ExtractedFactRead]) -> str:
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

    def _verifications_for_prompt(self, results: list[VerificationResultRead]) -> str:
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

    def _citations_for_prompt(self, citations: list[Citation]) -> str:
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

    def _status_for_fact(
        self,
        fact: ExtractedFactRead,
        verification_results: list[VerificationResultRead],
    ) -> str:
        for item in verification_results:
            if item.fact_id == fact.id:
                return str(item.status)
        return "unknown"

    def _truncate(self, text: str, limit: int) -> str:
        normalized = text.strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."
