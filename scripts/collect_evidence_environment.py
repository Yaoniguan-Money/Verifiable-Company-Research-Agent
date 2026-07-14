from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evidence" / "raw" / "environment.json"


def version(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip()


artifact = {
    "schema_version": 1,
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "python": sys.version,
    "platform": platform.platform(),
    "machine": platform.machine(),
    "processor": platform.processor(),
    "pytest": version([sys.executable, "-m", "pytest", "--version"]),
    "coverage": version([sys.executable, "-m", "coverage", "--version"]),
    "credential_presence": {
        name: bool(os.getenv(name))
        for name in [
            "DEEPSEEK_API_KEY",
            "QIANFAN_API_KEY",
            "QIANFAN_SECRET_KEY",
            "BAIDU_API_KEY",
            "DASHSCOPE_API_KEY",
        ]
    },
    "credential_values_recorded": False,
    "git_metadata_available": (ROOT / ".git").exists(),
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUTPUT)
