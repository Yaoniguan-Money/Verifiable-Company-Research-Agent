from __future__ import annotations

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
from app.services.report_renderer import MockReportRenderer, ReportRenderInput


class DeepSeekLLMProvider(LLMProvider):
    """DeepSeek OpenAI-compatible chat provider.

    真实模型只负责局部文本生成；事实抽取、证据链、报告结构和合规兜底仍由本地工程链路控制。
    """

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

    def extract_facts(
        self,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        # DeepSeek provider 当前不做隐式 mock fallback，避免真实模式“看起来成功但实际用了 mock”。
        return []

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
                "禁止输出买入/卖出/目标价/收益承诺/个性化投资建议。",
                f"当前日期：{datetime.now(timezone.utc).date().isoformat()}。不要把早于或等于当前年份的披露期间误判为未来期间。",
                f"企业：{company_name}",
                f"研究问题：{question}",
                "事实与验证状态：",
                *fact_lines,
                "请用中文输出一段审慎的风险观察，必须指出证据不足或冲突时的限制。",
            ]
        )
        return self._chat(prompt, max_tokens=700)

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
        # 报告结构仍由本地 renderer 控制，保证 citations/status 分区稳定。
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
    ) -> str:
        report_brief = report.content.strip().replace("\n", " ")
        if len(report_brief) > 1800:
            report_brief = report_brief[:1800] + "..."

        prompt = "\n".join(
            [
                "你是企业公开信息研究助手。回答必须严格基于当前报告，不得补充报告外常识、行业印象或未经引用的公开信息。",
                "禁止买入、卖出、加仓、减仓、目标价、收益承诺、个股推荐、个性化投资建议。",
                "如果当前报告证据不足，只说明报告内的证据缺口、已抽取事实、验证状态和可追溯来源限制。",
                "除非用户明确询问买卖/目标价/收益，否则不要声称当前请求涉及投资建议。",
                f"企业：{task.company_name}",
                f"用户追问：{message}",
                f"事实数量：{fact_count}",
                f"验证状态统计：{verification_counts}",
                f"报告摘要：{report_brief}",
                "请用中文回答，不要使用“常规公开信息”“过往公开披露内容”“一般性说明”等脱离当前报告的表达。",
            ]
        )
        return self._chat(prompt, max_tokens=800)

    def check_compliance(self, text: str) -> ComplianceCheckResult:
        # 合规兜底保持本地 deterministic，便于测试和回归。
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

    def _chat(self, prompt: str, *, max_tokens: int) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是审慎的企业公开信息研究助手，必须遵守非投资建议边界。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
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
            raise RuntimeError("DeepSeek API request failed") from exc

        try:
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("DeepSeek API returned an unexpected response shape") from exc
        text = str(content).strip()
        if not text:
            reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else None
            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            if str(reasoning_content or "").strip() and finish_reason == "length":
                raise RuntimeError(
                    "DeepSeek returned reasoning_content but no final message.content; "
                    "use deepseek-chat for smoke tests or increase max_tokens."
                )
            raise RuntimeError("DeepSeek API returned an empty response")
        return text

    def _status_for_fact(
        self,
        fact: ExtractedFactRead,
        verification_results: list[VerificationResultRead],
    ) -> str:
        for item in verification_results:
            if item.fact_id == fact.id:
                return str(item.status)
        return "unknown"
