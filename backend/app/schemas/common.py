"""Schema 公共类型与枚举。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SchemaBase(BaseModel):
    """所有 schema 的基础配置。"""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class IDSchema(SchemaBase):
    id: str = Field(..., description="主键 ID（UUID 字符串）")


class TimestampSchema(SchemaBase):
    created_at: datetime
    updated_at: datetime | None = None


class TaskStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, Enum):
    ANNUAL_REPORT = "annual_report"
    ANNOUNCEMENT = "announcement"
    OFFICIAL_PDF = "official_pdf"
    OFFICIAL_DISCLOSURE_PAGE = "official_disclosure_page"
    NEWS = "news"
    OFFICIAL_WEBSITE = "official_website"
    GOVERNMENT = "government"
    PATENT = "patent"
    HIRING = "hiring"
    OTHER = "other"


class SourceAuthority(str, Enum):
    HIGH = "high_authority"
    MEDIUM = "medium_authority"
    LOW = "low_authority"
    UNKNOWN = "unknown_authority"


class SourceLayer(str, Enum):
    """Evidence layer used by citation sorting and fact gates.

    Official PDFs/disclosure pages can support high-confidence facts. Entry pages
    are only navigation surfaces; third-party background stays lower priority.
    """

    OFFICIAL_PDF = "official_pdf"
    OFFICIAL_DISCLOSURE_PAGE = "official_disclosure_page"
    OFFICIAL_ENTRY_PAGE = "official_entry_page"
    THIRD_PARTY_BACKGROUND = "third_party_background"


class ContentFetchStatus(str, Enum):
    FETCHED_CONTENT = "fetched_content"
    ENTRY_PAGE_ONLY = "entry_page_only"
    CONTENT_INSUFFICIENT = "content_insufficient"
    SNIPPET_ONLY = "snippet_only"


SOURCE_LAYER_METADATA_KEY = "source_layer"
CONTENT_FETCH_STATUS_METADATA_KEY = "content_fetch_status"
SOURCE_METADATA_KEY = "source_metadata"
SOURCE_CREDIBILITY_SCORE_METADATA_KEY = "source_credibility_score"

HIGH_AUTHORITY_THRESHOLD = 0.85
LOW_AUTHORITY_THRESHOLD = 0.6


def authority_label(score: float | None) -> SourceAuthority:
    if score is None:
        return SourceAuthority.UNKNOWN
    if score >= HIGH_AUTHORITY_THRESHOLD:
        return SourceAuthority.HIGH
    if score < LOW_AUTHORITY_THRESHOLD:
        return SourceAuthority.LOW
    return SourceAuthority.MEDIUM


def normalize_source_layer(layer: object) -> SourceLayer:
    if isinstance(layer, SourceLayer):
        return layer
    try:
        return SourceLayer(str(layer))
    except ValueError:
        return SourceLayer.THIRD_PARTY_BACKGROUND


def source_layer_from_metadata(source_metadata: dict | None) -> SourceLayer:
    if not source_metadata:
        return SourceLayer.THIRD_PARTY_BACKGROUND
    return normalize_source_layer(source_metadata.get(SOURCE_LAYER_METADATA_KEY))


def source_layer_priority(layer: object) -> int:
    if isinstance(layer, SourceLayer):
        normalized = layer
    else:
        try:
            normalized = SourceLayer(str(layer))
        except ValueError:
            return 2
    return {
        SourceLayer.OFFICIAL_PDF: 4,
        SourceLayer.OFFICIAL_DISCLOSURE_PAGE: 4,
        SourceLayer.OFFICIAL_ENTRY_PAGE: 3,
        SourceLayer.THIRD_PARTY_BACKGROUND: 1,
    }[normalized]


def is_official_body_layer(layer: object) -> bool:
    return normalize_source_layer(layer) in {
        SourceLayer.OFFICIAL_PDF,
        SourceLayer.OFFICIAL_DISCLOSURE_PAGE,
    }


def blocks_high_confidence_fact(*, source_metadata: dict | None, credibility_score: object) -> bool:
    if source_layer_from_metadata(source_metadata) == SourceLayer.OFFICIAL_ENTRY_PAGE:
        return True
    try:
        return credibility_score is not None and float(credibility_score) < LOW_AUTHORITY_THRESHOLD
    except (TypeError, ValueError):
        return False


def source_quality_counts(
    sources: list[object],
) -> tuple[dict[str, int], dict[str, int]]:
    authority_counts = {
        SourceAuthority.HIGH.value: 0,
        SourceAuthority.MEDIUM.value: 0,
        SourceAuthority.LOW.value: 0,
        SourceAuthority.UNKNOWN.value: 0,
    }
    layer_counts = {
        SourceLayer.OFFICIAL_PDF.value: 0,
        SourceLayer.OFFICIAL_DISCLOSURE_PAGE.value: 0,
        SourceLayer.OFFICIAL_ENTRY_PAGE.value: 0,
        SourceLayer.THIRD_PARTY_BACKGROUND.value: 0,
    }
    for source in sources:
        authority = authority_label(getattr(source, "credibility_score", None))
        authority_counts[authority.value] += 1
        layer = source_layer_from_metadata(getattr(source, "source_metadata", None))
        layer_counts[layer.value] += 1
    return authority_counts, layer_counts


def source_quality_insufficient(sources: list[object]) -> bool:
    if not sources:
        return True
    authority_counts, layer_counts = source_quality_counts(sources)
    total = len(sources)
    low_count = authority_counts[SourceAuthority.LOW.value]
    has_high_authority = authority_counts[SourceAuthority.HIGH.value] > 0
    has_official_body = (
        layer_counts[SourceLayer.OFFICIAL_PDF.value]
        + layer_counts[SourceLayer.OFFICIAL_DISCLOSURE_PAGE.value]
        > 0
    )
    return not has_high_authority and not has_official_body and (low_count / total) >= 0.5


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    INSUFFICIENT = "insufficient"
    OUTDATED = "outdated"
    REJECTED = "rejected"


class ComplianceStatus(str, Enum):
    PASSED = "passed"
    REWRITTEN = "rewritten"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
