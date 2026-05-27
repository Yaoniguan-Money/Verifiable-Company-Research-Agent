from __future__ import annotations

from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_docs_should_keep_mvp_boundary_instead_of_production_claims() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = _read(root / "README.md")
    provider_boundary = _read(root / "docs" / "provider_boundary.md")
    api_doc = _read(root / "docs" / "api.md")

    assert "开源 MVP" in readme
    assert "provider 可替换" in readme or "可替换 provider" in readme
    assert "可选真实链路示例" in readme
    assert "默认示例" in provider_boundary
    assert "这些样例用于链路回归" in readme
    assert "不是生产级向量数据库" in api_doc
    assert "local_hashing" in readme
    assert "不提供投资建议" in readme
