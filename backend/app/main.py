"""FastAPI application entrypoint.

启动方式（项目根目录下）：
    uvicorn app.main:app --reload --app-dir backend

或使用 .env 中配置的 host/port：
    python -m backend.app.main

当前口径：开源 MVP / reference implementation。
- 默认 workflow engine 是 LangGraph，service engine 仅作为 legacy regression fallback。
- 默认 SearchProvider 走联网公开来源；外部付费/带 key provider 通过配置显式启用。
- 当前实现不是生产级投研系统，也不提供投资建议。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import admin, health
from app.api.routes import chat, facts, research, sources, verification
from app.core.config import get_settings
from app.db.init_db import init_db
from app.observability.logging import configure_structlog

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动时校验配置、初始化数据库；退出时仅打 info 日志。"""
    settings = get_settings()
    # 启动期先把 provider key 校验跑一遍，避免上线后才发现 mock fallback。
    settings.validate_runtime_provider_requirements()
    logger.info(
        "启动配置 app=%s | llm=%s search=%s embedding=%s | "
        "qianfan_key=%s deepseek_key=%s baidu_search_key=%s",
        settings.app_name,
        settings.llm_provider,
        settings.search_provider,
        settings.embedding_provider,
        settings.has_qianfan_api_key,
        settings.has_deepseek_api_key,
        settings.has_baidu_ai_search_api_key,
    )
    init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Application shutting down.")


def create_app() -> FastAPI:
    """工厂函数。便于测试时创建独立实例，也便于未来按环境装配不同中间件。"""
    settings = get_settings()

    configure_structlog(settings.log_level)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "可溯源企业公开信息研究智能体 —— 基于公开资料进行信息检索、证据抽取、"
            "交叉验证与可引用研究报告生成。本系统【不提供】买卖建议、目标价、"
            "收益预测或个股推荐。详见 docs/compliance.md。"
        ),
        lifespan=lifespan,
    )

    if settings.is_dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(admin.router)
    app.include_router(health.router)
    app.add_api_route(
        "/health/providers",
        health.health_providers,
        methods=["GET"],
        response_model=health.ProvidersHealthResponse,
        summary="Provider 健康检查",
        tags=["meta"],
    )
    app.include_router(chat.router)
    app.include_router(research.router)
    app.include_router(sources.router)
    app.include_router(facts.router)
    app.include_router(verification.router)

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_dev,
        app_dir="backend",
    )
