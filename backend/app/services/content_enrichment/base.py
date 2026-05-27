from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.source import SourceRead


@dataclass
class EnrichedContent:
    raw: str
    parsed: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ContentEnricher(ABC):
    @abstractmethod
    def enrich(self, content: EnrichedContent, source: SourceRead, question: str) -> EnrichedContent: ...

    @abstractmethod
    def supports(self, source: SourceRead, content: EnrichedContent | None = None) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
