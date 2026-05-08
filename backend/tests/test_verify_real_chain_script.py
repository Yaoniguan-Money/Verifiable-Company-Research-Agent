"""verify_real_chain.py 中 embedding 策略相关测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODNAME = "_verify_real_chain_loaded_for_tests"
_SPEC = importlib.util.spec_from_file_location(_MODNAME, _ROOT / "scripts" / "verify_real_chain.py")
assert _SPEC and _SPEC.loader
_VRC = importlib.util.module_from_spec(_SPEC)
sys.modules[_MODNAME] = _VRC
_SPEC.loader.exec_module(_VRC)


def test_assert_embedding_mode_rejects_local_hashing_by_default() -> None:
    with pytest.raises(RuntimeError, match="local_hashing"):
        _VRC.assert_embedding_mode_for_real_chain(
            {"embedding_provider": "local_hashing"},
            allow_local_embedding=False,
        )


def test_assert_embedding_mode_allow_local_only_warns(capsys: pytest.CaptureFixture[str]) -> None:
    _VRC.assert_embedding_mode_for_real_chain(
        {"embedding_provider": "local_hashing"},
        allow_local_embedding=True,
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "local_hashing" in captured.out


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert _VRC.normalize_base_url(" http://localhost:8000/ ") == "http://localhost:8000"


def test_normalize_base_url_rejects_blank_or_non_http() -> None:
    with pytest.raises(ValueError, match="blank"):
        _VRC.normalize_base_url("  ")
    with pytest.raises(ValueError, match="http"):
        _VRC.normalize_base_url("localhost:8000")
