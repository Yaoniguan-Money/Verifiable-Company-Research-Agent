"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量 / .env 加载的应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    app_name: str = Field(default="Verifiable Company Research Agent")
    app_env: Literal["dev", "test", "prod"] = Field(default="dev")
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # ---------- Compliance ----------
    compliance_strict_mode: bool = Field(default=True)
    compliance_block_on_violation: bool = Field(default=True)

    # ---------- Database ----------
    database_url: str = Field(default="sqlite:///./data/dev.db")
    db_echo: bool = Field(default=False)

    # ---------- Provider selection ----------
    llm_provider: Literal["mock", "deepseek", "qianfan"] = Field(default="mock")
    search_provider: Literal[
        "mock",
        "local_documents",
        "official_urls",
        "baidu_ai_search",
        "cninfo_announcements",
        "public_sources",
    ] = Field(default="public_sources")
    local_documents_dir: str = Field(default="./data/imports")
    official_url_allowed_domains: str = Field(default="")
    official_url_timeout_seconds: float = Field(default=15.0, gt=0)
    baidu_ai_search_api_key: SecretStr | None = Field(default=None)
    baidu_ai_search_endpoint: str = Field(
        default="https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    )
    baidu_ai_search_model: str = Field(default="ernie-4.5-turbo-32k")
    baidu_ai_search_top_k: int = Field(default=5, ge=1, le=10)
    baidu_ai_search_timeout_seconds: float = Field(default=30.0, gt=0)
    baidu_ai_search_fetch_reference_pages: bool = Field(default=True)
    baidu_ai_search_enable_deep_search: bool = Field(default=False)
    cninfo_timeout_seconds: float = Field(default=30.0, gt=0)
    cninfo_top_k: int = Field(default=4, ge=1, le=12)
    cninfo_lookback_years: int = Field(default=4, ge=1, le=10)
    cninfo_max_source_chars: int = Field(default=80_000, ge=10_000)
    embedding_provider: Literal["mock", "local_hashing", "dashscope", "siliconflow"] = Field(
        default="local_hashing"
    )
    embedding_api_key: SecretStr | None = Field(default=None)
    embedding_base_url: str | None = Field(default=None)
    embedding_model: str | None = Field(default=None)
    embedding_dimension: int | None = Field(default=None)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_max_batch_size: int = Field(default=10, ge=1)
    vector_store: Literal["in_memory", "sqlite"] = Field(default="in_memory")
    mock_embedding_dimension: int = Field(default=8, ge=1)
    local_embedding_dimension: int = Field(default=128, ge=8)
    vector_store_sqlite_path: str = Field(default="./data/vector_store.sqlite")

    # ---------- Workflow ----------
    # Default orchestration is LangGraph; service remains only as a legacy fallback.
    workflow_engine: Literal["service", "langgraph"] = Field(default="langgraph")
    workflow_chunk_size: int = Field(default=1600, ge=20)
    workflow_chunk_overlap: int = Field(default=180, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1)

    # ---------- DeepSeek LLM ----------
    deepseek_api_key: SecretStr | None = Field(default=None)
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---------- Qianfan LLM ----------
    qianfan_api_key: SecretStr | None = Field(default=None)
    qianfan_base_url: str = Field(default="https://qianfan.baidubce.com/v2")
    qianfan_model: str = Field(default="ernie-4.5-8k-preview")
    qianfan_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("embedding_dimension", mode="before")
    @classmethod
    def optional_embedding_dimension(cls, value: object) -> object:
        """空字符串视为未配置（None）。"""
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return None if stripped == "" else stripped
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def embedding_dimension_positive_when_set(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise ValueError("EMBEDDING_DIMENSION must be >= 1 when set")
        return value

    @field_validator("llm_provider", "search_provider", "embedding_provider", mode="before")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        return str(value).strip().lower()

    @property
    def official_url_domain_list(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.official_url_allowed_domains.split(",")
            if item.strip()
        ]

    @property
    def db_scheme(self) -> str:
        """从 database_url 中提取 scheme（如 sqlite / postgresql），用于健康检查暴露。

        永远不要把完整 url 暴露给外部，里面可能含密码。
        """
        return self.database_url.split("://", 1)[0] if "://" in self.database_url else "unknown"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def has_qianfan_api_key(self) -> bool:
        return (
            self.qianfan_api_key is not None
            and bool(self.qianfan_api_key.get_secret_value().strip())
        )

    @property
    def has_deepseek_api_key(self) -> bool:
        return (
            self.deepseek_api_key is not None
            and bool(self.deepseek_api_key.get_secret_value().strip())
        )

    @property
    def has_baidu_ai_search_api_key(self) -> bool:
        return (
            self.baidu_ai_search_api_key is not None
            and bool(self.baidu_ai_search_api_key.get_secret_value().strip())
        )

    @property
    def has_embedding_api_key(self) -> bool:
        return (
            self.embedding_api_key is not None
            and bool(self.embedding_api_key.get_secret_value().strip())
        )

    @property
    def embedding_dimension_configured(self) -> bool:
        return self.embedding_dimension is not None

    @property
    def embedding_base_url_explicitly_set(self) -> bool:
        """是否在环境变量中显式配置了非空 ``EMBEDDING_BASE_URL``（未配置则仅用推荐默认值）。"""
        return (self.embedding_base_url or "").strip() != ""

    @property
    def resolved_embedding_base_url(self) -> str | None:
        """dashscope/siliconflow：未配置时使用推荐默认值；其它 provider 为 None。"""
        if self.embedding_provider == "dashscope":
            v = (self.embedding_base_url or "").strip()
            return v or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if self.embedding_provider == "siliconflow":
            v = (self.embedding_base_url or "").strip()
            return v or "https://api.siliconflow.cn/v1"
        return None

    @property
    def resolved_embedding_model(self) -> str | None:
        """dashscope/siliconflow：未配置时使用推荐默认值；其它 provider 为 None。"""
        if self.embedding_provider == "dashscope":
            v = (self.embedding_model or "").strip()
            return v or "text-embedding-v4"
        if self.embedding_provider == "siliconflow":
            v = (self.embedding_model or "").strip()
            return v or "BAAI/bge-m3"
        return None

    @property
    def health_embedding_model_display(self) -> str:
        """health / 脚本展示的模型标识（不含密钥）。"""
        if self.embedding_provider == "mock":
            return "mock"
        if self.embedding_provider == "local_hashing":
            return "local_hashing"
        r = self.resolved_embedding_model
        return r or ""

    def validate_runtime_provider_requirements(self) -> None:
        if self.llm_provider == "qianfan" and not self.has_qianfan_api_key:
            raise ValueError("QIANFAN_API_KEY is required when LLM_PROVIDER=qianfan")
        if self.llm_provider == "deepseek" and not self.has_deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        if self.search_provider == "baidu_ai_search" and not self.has_baidu_ai_search_api_key:
            raise ValueError(
                "BAIDU_AI_SEARCH_API_KEY is required when SEARCH_PROVIDER=baidu_ai_search"
            )
        if self.embedding_provider in ("dashscope", "siliconflow") and not self.has_embedding_api_key:
            raise ValueError(
                "EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=dashscope or siliconflow"
            )


@lru_cache
def get_settings() -> Settings:
    """单例返回 Settings。lru_cache 保证全应用只初始化一次。

    在测试中如需 override，调用 ``get_settings.cache_clear()`` 后重建即可。
    """
    return Settings()
