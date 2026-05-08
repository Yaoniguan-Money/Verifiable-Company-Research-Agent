"""Manual Qianfan connectivity probe.

This is not part of CI or the default real-chain validation path. It exists only
for local debugging when `LLM_PROVIDER=qianfan` is explicitly configured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    if settings.qianfan_api_key is None:
        print("缺少 QIANFAN_API_KEY。请先在本地 .env 或当前 shell 中设置后再运行。")
        return 2

    api_key = settings.qianfan_api_key.get_secret_value()
    payload: dict[str, Any] = {
        "model": settings.qianfan_model,
        "messages": [
            {"role": "system", "content": "你是连通性测试助手。"},
            {"role": "user", "content": "只回答：连接成功"},
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    try:
        with httpx.Client(timeout=settings.qianfan_timeout_seconds) as client:
            response = client.post(
                f"{settings.qianfan_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        print(f"Qianfan API 连通测试失败：{exc}")
        return 1

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("Qianfan API 返回结构不符合预期。")
        return 1

    print(str(content).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
