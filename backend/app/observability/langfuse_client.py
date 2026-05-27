"""LangFuse 可选集成。"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app.core.config import get_settings

F = TypeVar("F", bound=Callable[..., Any])


def maybe_observe(name: str | None = None) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        settings = get_settings()
        if not settings.effective("langfuse_enabled"):
            return fn

        try:
            from langfuse.decorators import observe  # type: ignore[import-untyped]
        except ImportError:
            return fn

        return observe(name=name or fn.__name__)(fn)  # type: ignore[return-value]

    return decorator
