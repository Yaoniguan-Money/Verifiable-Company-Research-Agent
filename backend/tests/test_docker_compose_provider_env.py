from __future__ import annotations

from pathlib import Path


def test_docker_compose_does_not_fallback_provider_to_mock() -> None:
    compose_file = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    content = compose_file.read_text(encoding="utf-8")

    assert "LLM_PROVIDER: ${LLM_PROVIDER:-mock}" not in content
    assert "SEARCH_PROVIDER: ${SEARCH_PROVIDER:-mock}" not in content
    assert "EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-mock}" not in content
