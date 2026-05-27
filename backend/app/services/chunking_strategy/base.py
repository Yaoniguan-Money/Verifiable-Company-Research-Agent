from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ChunkMetadata:
    source_title: str = ""
    source_url: str | None = None
    source_type: str = ""
    retrieved_at: datetime | None = None
    enrichment_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkingPart:
    chunk_index: int
    text: str
    metadata: dict[str, Any]


class ChunkingStrategy(ABC):
    @abstractmethod
    def split(self, text: str, metadata: ChunkMetadata) -> list[ChunkingPart]: ...

    @property
    @abstractmethod
    def strategy_name(self) -> str: ...
