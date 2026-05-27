from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.db.models import VerificationStatus as VerificationStatusORM
from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.chunk import Citation
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerPipeline
from app.services.question_time_scope import resolve_research_time_scope


@dataclass(slots=True)
class ReportFactBuckets:
    verified: list[ExtractedFactRead] = field(default_factory=list)
    conflicted: list[ExtractedFactRead] = field(default_factory=list)
    insufficient: list[ExtractedFactRead] = field(default_factory=list)
    outdated: list[ExtractedFactRead] = field(default_factory=list)
    rejected: list[ExtractedFactRead] = field(default_factory=list)


class ReportAssemblyService:
    """Build report payloads from task facts, verification results, and citations."""

    def __init__(self, db: Session, llm_provider: LLMProvider | None = None) -> None:
        self.db = db
        self.llm_provider = llm_provider or ProviderFactory().create_llm_provider()
        self.artifacts = ResearchArtifactRepository(db)

    def build_report(
        self,
        *,
        task: ResearchTask,
        risk_analysis: str,
        citations: list[Citation],
    ) -> ReportCreate:
        facts = self._list_facts(task.id)
        verifications = self._list_verifications(task.id)
        verification_reads = [
            VerificationResultRead.model_validate(item) for item in verifications
        ]
        buckets = self._bucket_facts(facts=facts, verifications=verifications)
        buckets.verified = self._rank_verified_facts(task.id, buckets.verified)
        time_scope = resolve_research_time_scope(
            task.question,
            llm_provider=self.llm_provider,
            allow_llm=True,
        )
        answer_context = AnswerPipeline().build_context(
            company_name=task.company_name,
            question=task.question,
            verified_facts=buckets.verified,
            conflicted_facts=buckets.conflicted,
            verifications=verification_reads,
            time_scope=time_scope,
        )

        report_kwargs = dict(
            task=ResearchTaskRead.model_validate(task),
            verified_facts=buckets.verified,
            conflicted_facts=buckets.conflicted,
            insufficient_facts=buckets.insufficient,
            verification_results=verification_reads,
            risk_analysis=risk_analysis,
            citations=citations,
            outdated_facts=buckets.outdated,
            rejected_facts=buckets.rejected,
            core_facts=answer_context.primary_facts,
            supporting_facts=answer_context.optional_context_facts,
            relevance_intents=answer_context.plan.intent_labels,
            reader_summary=answer_context.summary_text,
            answer_context=answer_context,
        )
        try:
            return self.llm_provider.generate_report(**report_kwargs)
        except TypeError:
            report_kwargs.pop("answer_context", None)
            return self.llm_provider.generate_report(**report_kwargs)

    def _list_facts(self, task_id: str) -> list[ExtractedFact]:
        return self.artifacts.list_facts(task_id)

    def _list_verifications(self, task_id: str) -> list[VerificationResult]:
        return self.artifacts.list_verifications(task_id)

    def _bucket_facts(
        self,
        *,
        facts: list[ExtractedFact],
        verifications: list[VerificationResult],
    ) -> ReportFactBuckets:
        verification_by_fact = {item.fact_id: item for item in verifications}
        buckets = ReportFactBuckets()

        for fact in facts:
            read = ExtractedFactRead.model_validate(fact)
            ver = verification_by_fact.get(fact.id)
            if ver and ver.status == VerificationStatusORM.VERIFIED.value:
                buckets.verified.append(read)
            elif ver and ver.status == VerificationStatusORM.CONFLICTED.value:
                buckets.conflicted.append(read)
            elif ver and ver.status == VerificationStatusORM.OUTDATED.value:
                buckets.outdated.append(read)
            elif ver and ver.status == VerificationStatusORM.REJECTED.value:
                buckets.rejected.append(read)
            else:
                buckets.insufficient.append(read)

        return buckets

    def _rank_verified_facts(
        self,
        task_id: str,
        facts: list[ExtractedFactRead],
    ) -> list[ExtractedFactRead]:
        source_map = self.artifacts.source_map(task_id)
        disclosure_rank = {
            "annual": 0,
            "semi_annual": 1,
            "interim": 2,
            "media": 3,
        }

        def key(fact: ExtractedFactRead) -> tuple[int, int, float]:
            source = source_map.get(fact.source_id)
            metadata = getattr(source, "source_metadata", None) or {}
            kind = str(metadata.get("disclosure_kind") or "interim")
            published_at = getattr(source, "published_at", None)
            timestamp = published_at.timestamp() if published_at else 0.0
            return (disclosure_rank.get(kind, 2), -int(timestamp), -float(fact.confidence or 0))

        return sorted(facts, key=key)
