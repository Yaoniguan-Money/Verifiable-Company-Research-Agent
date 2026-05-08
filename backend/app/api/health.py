"""健康检查端点。

用于：
- 验证服务进程存活
- 验证配置中心可读取
- 支持 docker-compose / k8s 探针复用
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import Settings, get_settings
from app.providers.embedding.openai_compatible_provider import embedding_base_url_host

router = APIRouter(prefix="/api", tags=["meta"])


class HealthResponse(BaseModel):
    """健康检查返回体 —— 结构化输出，避免裸字符串。"""

    status: str
    app_name: str
    version: str
    env: str
    compliance_strict_mode: bool
    db_scheme: str  # 仅暴露 scheme，不暴露完整 URL 防止泄漏密码


class ProvidersHealthResponse(BaseModel):
    llm_provider: str
    search_provider: str
    embedding_provider: str
    embedding_model: str
    embedding_api_key_configured: bool
    embedding_base_url_configured: bool
    embedding_base_url_host: str | None
    embedding_dimension_configured: bool
    embedding_max_batch_size: int
    qianfan_api_key_configured: bool
    deepseek_api_key_configured: bool
    baidu_ai_search_api_key_configured: bool
    mock_enabled: bool


@router.get("/health", response_model=HealthResponse, summary="服务健康检查")
def health() -> HealthResponse:
    settings: Settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=__version__,
        env=settings.app_env,
        compliance_strict_mode=settings.compliance_strict_mode,
        db_scheme=settings.db_scheme,
    )


@router.get("/health/providers", response_model=ProvidersHealthResponse, summary="Provider 健康检查")
def health_providers() -> ProvidersHealthResponse:
    settings: Settings = get_settings()
    em_host: str | None = None
    if settings.embedding_provider in ("dashscope", "siliconflow"):
        em_host = embedding_base_url_host(settings.resolved_embedding_base_url)
    return ProvidersHealthResponse(
        llm_provider=settings.llm_provider,
        search_provider=settings.search_provider,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.health_embedding_model_display,
        embedding_api_key_configured=settings.has_embedding_api_key,
        embedding_base_url_configured=settings.embedding_base_url_explicitly_set,
        embedding_base_url_host=em_host,
        embedding_dimension_configured=settings.embedding_dimension_configured,
        embedding_max_batch_size=settings.embedding_max_batch_size,
        qianfan_api_key_configured=settings.has_qianfan_api_key,
        deepseek_api_key_configured=settings.has_deepseek_api_key,
        baidu_ai_search_api_key_configured=settings.has_baidu_ai_search_api_key,
        mock_enabled=(
            settings.llm_provider == "mock"
            or settings.search_provider == "mock"
            or settings.embedding_provider == "mock"
        ),
    )
