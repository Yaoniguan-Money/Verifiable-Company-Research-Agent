from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MODNAME = "_public_company_regression_script_loaded_for_tests"
_SPEC = importlib.util.spec_from_file_location(
    _MODNAME,
    _ROOT / "scripts" / "run_public_company_regression.py",
)
assert _SPEC and _SPEC.loader
_PCR = importlib.util.module_from_spec(_SPEC)
sys.modules[_MODNAME] = _PCR
_SPEC.loader.exec_module(_PCR)


def test_live_cases_are_loaded_from_json_file(tmp_path: Path) -> None:
    case_file = tmp_path / "live_cases.json"
    case_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "sample_case",
                        "company_name": "Example Public Company",
                        "question": "Summarize operating risks from public sources.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = _PCR._load_live_cases(case_file)

    assert cases["sample_case"]["company_name"] == "Example Public Company"
    assert cases["sample_case"]["question"] == "Summarize operating risks from public sources."


def test_live_regression_cases_are_not_embedded_in_script() -> None:
    source = (_ROOT / "scripts" / "run_public_company_regression.py").read_text(encoding="utf-8")

    assert "FIXED_EVALUATION_CASES" not in source
    assert "小米集团" not in source
    assert "腾讯控股" not in source
    assert "比亚迪" not in source
