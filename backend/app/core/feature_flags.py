"""运行时特性开关覆盖层。

所有默认关闭的功能可通过 API 一键开启，重启后恢复默认。
生产环境不建议开启此能力，通过 .env 持久化配置。
"""

from __future__ import annotations

from threading import Lock
from typing import Any

_mutex = Lock()
_overrides: dict[str, Any] = {}

# 允许动态切换的开关列表
ALLOWED_FLAGS: dict[str, dict[str, Any]] = {
    "hybrid_retrieval_llm_rewrite": {
        "label": "LLM Query 改写",
        "description": "Hybrid RAG 中启用 LLM 查询改写与子问题拆解",
        "default": False,
    },
    "langfuse_enabled": {
        "label": "LangFuse 可观测性",
        "description": "将 LLM 调用 trace 上报到 LangFuse（需先启动 langfuse 容器）",
        "default": False,
    },
    "reranker_backend": {
        "label": "Reranker 后端",
        "description": "检索重排后端：lexical（词面重叠，CPU）、onnx（cross-encoder）或 embedding（复用 Embedding API）",
        "default": "embedding",
        "options": ["lexical", "onnx", "embedding"],
    },
    "llm_streaming_enabled": {
        "label": "LLM 流式输出",
        "description": "启用 LLM streaming（逐 token 推送）",
        "default": True,
    },
    "hybrid_retrieval_enabled": {
        "label": "Hybrid RAG 检索",
        "description": "启用 Dense + BM25 混合检索 + RRF 融合 + Rerank",
        "default": True,
    },
}


def set_flag(name: str, value: Any) -> bool:
    """设置一个特性开关的值。返回是否成功。"""
    if name not in ALLOWED_FLAGS:
        return False
    with _mutex:
        _overrides[name] = value
    return True


def get_flag(name: str) -> Any | None:
    """获取特性开关的运行时覆盖值，未设置则返回 None。"""
    with _mutex:
        return _overrides.get(name)


def get_all_flags() -> dict[str, Any]:
    """获取所有特性开关的当前值。优先级：运行时覆盖 > .env 配置 > 代码默认值。"""
    from app.core.config import get_settings
    settings = get_settings()
    result: dict[str, Any] = {}
    with _mutex:
        for name, meta in ALLOWED_FLAGS.items():
            result[name] = _overrides.get(name, getattr(settings, name, meta["default"]))
    return result


def resolve_flag(name: str, settings_value: Any) -> Any:
    """解析特性开关：运行时覆盖优先，否则用 settings 值。"""
    with _mutex:
        if name in _overrides:
            return _overrides[name]
    return settings_value


def reset_all() -> None:
    """重置所有运行时覆盖。"""
    with _mutex:
        _overrides.clear()
