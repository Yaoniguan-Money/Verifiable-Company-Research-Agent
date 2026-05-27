from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from app.providers.search.base import SearchProvider
from app.schemas.common import SourceType
from app.schemas.source import SourceCreate


class LocalDocumentSearchProvider(SearchProvider):
    """从本地 txt/md 导入公开资料，用作真实搜索接入前的可复现数据源。"""

    SUPPORTED_SUFFIXES = {".txt", ".md"}

    def __init__(self, root_dir: str = "./data/imports") -> None:
        self.root_dir = Path(root_dir)

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        files = self._candidate_files(company_name)
        now = datetime.now(timezone.utc)
        out: list[SourceCreate] = []
        for path in files:
            metadata, body = self._read_document(path)
            if not body.strip():
                continue
            out.append(
                SourceCreate(
                    task_id="TBD_BY_WORKFLOW",
                    title=metadata.get("title") or path.stem.replace("_", " "),
                    url=metadata.get("url"),
                    source_type=self._source_type(metadata.get("source_type")),
                    published_at=self._parse_datetime(metadata.get("published_at")),
                    retrieved_at=now,
                    raw_content=body.strip(),
                    credibility_score=self._parse_score(metadata.get("credibility_score")),
                )
            )
        if not out:
            raise ValueError(
                f"No local public documents found for {company_name!r} under {self.root_dir}"
            )
        return out

    def _candidate_files(self, company_name: str) -> list[Path]:
        dirs = [self.root_dir / company_name, self.root_dir / self._slug(company_name)]
        files: list[Path] = []
        for directory in dirs:
            if directory.exists():
                files.extend(
                    p
                    for p in directory.rglob("*")
                    if p.is_file() and p.suffix.lower() in self.SUPPORTED_SUFFIXES
                )
        if not files and self.root_dir.exists():
            files.extend(
                p
                for p in self.root_dir.iterdir()
                if p.is_file() and p.suffix.lower() in self.SUPPORTED_SUFFIXES
            )
        return sorted(set(files))

    def _read_document(self, path: Path) -> tuple[dict[str, str], str]:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        metadata: dict[str, str] = {}
        for line in parts[1].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"').strip("'")
        return metadata, parts[2]

    def _source_type(self, raw: str | None) -> SourceType:
        if not raw:
            return SourceType.OTHER
        try:
            return SourceType(raw)
        except ValueError:
            return SourceType.OTHER

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _parse_score(self, raw: str | None) -> float | None:
        if not raw:
            return 0.8
        try:
            score = float(raw)
        except ValueError:
            return 0.8
        if not isfinite(score):
            return 0.8
        return max(0.0, min(1.0, score))

    def _slug(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
