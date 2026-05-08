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
from app.services.fact_relevance import FactRelevanceService


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
        buckets = self._bucket_facts(facts=facts, verifications=verifications)
        relevance = FactRelevanceService().classify(
            question=task.question,
            facts=[
                *buckets.verified,
                *buckets.conflicted,
                *buckets.insufficient,
            ],
        )

        return self.llm_provider.generate_report(
            task=ResearchTaskRead.model_validate(task),
            verified_facts=buckets.verified,
            conflicted_facts=buckets.conflicted,
            insufficient_facts=buckets.insufficient,
            verification_results=[
                VerificationResultRead.model_validate(item) for item in verifications
            ],
            risk_analysis=risk_analysis,
            citations=citations,
            outdated_facts=buckets.outdated,
            rejected_facts=buckets.rejected,
            core_facts=relevance.core_facts,
            supporting_facts=relevance.supporting_facts,
            relevance_intents=relevance.intent_labels,
        )

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
