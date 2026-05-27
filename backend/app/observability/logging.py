"""结构化日志（structlog）。"""

from __future__ import annotations

import logging


def configure_structlog(level: str = "INFO") -> None:
    try:
        import structlog  # type: ignore[import-untyped]
    except ImportError:
        logging.basicConfig(level=level)
        return

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
    )
