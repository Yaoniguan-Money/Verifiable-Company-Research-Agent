"""应用配置：从环境变量 / ``.env`` 加载所有 provider、workflow、合规相关参数。

设计原则
--------
- **不在代码里硬编码生产密钥与服务地址**：所有可变值都映射到 `Field(default=...)`，
  外部部署只改 `.env`，不改源码。
- **默认值偏保守**：LLM 走 `mock`、Embedding 走 `local_hashing`，避免拉起即调用付费 API。
- **provider 缺 key 即拒绝启动**：`validate_runtime_provider_requirements` 在 lifespan 里
  调用一次；外部脚本（factory）也会同步调用，保证不会静默回退。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 各 provider 的公开常量（不是密钥）。``.env`` 给空字符串时 ``resolved_*``
# property 会回退到这些值，避免 default 被 pydantic-settings 的空字符串覆盖。
_DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_DASHSCOPE_MODEL = "text-embedding-v4"
_DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
_DEFAULT_SILICONFLOW_MODEL = "BAAI/bge-m3"

_DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
_DEFAULT_QIANFAN_BASE_URL = "https://qianfan.baidubce.com/v2"
_DEFAULT_QIANFAN_MODEL = "ernie-4.5-8k-preview"
_DEFAULT_BAIDU_AI_SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
_DEFAULT_BAIDU_AI_SEARCH_MODEL = "ernie-4.5-turbo-32k"


def _resolve_text(value: str | None, fallback: str) -> str:
    """如果 ``value`` 为空或仅空白则回退到 ``fallback``。"""
    return (value or "").strip() or fallback


def _has_secret(value: SecretStr | None) -> bool:
    """统一判断 SecretStr 是否真正包含内容（非 None 且 strip 后非空）。"""
    return value is not None and bool(value.get_secret_value().strip())


class Settings(BaseSettings):
    """应用所有可调参数的单一入口。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用基础 ----------
    app_name: str = Field(default="Verifiable Company Research Agent")
    app_env: Literal["dev", "test", "prod"] = Field(default="dev")
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # ---------- 合规策略 ----------
    compliance_strict_mode: bool = Field(default=True)
    compliance_block_on_violation: bool = Field(default=True)
    verification_treat_single_source_value_conflict: bool = Field(default=True)

    # ---------- 数据库 / 缓存 ----------
    database_url: str = Field(default="sqlite:///./data/dev.db")
    db_echo: bool = Field(default=False)
    use_alembic_on_startup: bool = Field(default=False)
    redis_url: str | None = Field(default=None)
    search_cache_ttl_seconds: int = Field(default=86_400, ge=60)

    # ---------- Provider 选型 ----------
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

    # ---- 百度 AI 搜索 ----
    baidu_ai_search_api_key: SecretStr | None = Field(default=None)
    baidu_ai_search_endpoint: str = Field(
        default="https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    )
    baidu_ai_search_model: str = Field(default="ernie-4.5-turbo-32k")
    baidu_ai_search_top_k: int = Field(default=5, ge=1, le=10)
    baidu_ai_search_timeout_seconds: float = Field(default=30.0, gt=0)
    baidu_ai_search_fetch_reference_pages: bool = Field(default=True)
    baidu_ai_search_enable_deep_search: bool = Field(default=False)

    # ---- 巨潮资讯（A 股公告）----
    cninfo_timeout_seconds: float = Field(default=30.0, gt=0)
    cninfo_top_k: int = Field(default=4, ge=1, le=12)
    cninfo_lookback_years: int = Field(default=4, ge=1, le=10)
    cninfo_max_source_chars: int = Field(default=80_000, ge=10_000)

    # ---- Embedding ----
    embedding_provider: Literal["mock", "local_hashing", "dashscope", "siliconflow"] = Field(
        default="local_hashing"
    )
    embedding_api_key: SecretStr | None = Field(default=None)
    embedding_base_url: str | None = Field(default=None)
    embedding_model: str | None = Field(default=None)
    embedding_dimension: int | None = Field(default=None)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_max_batch_size: int = Field(default=10, ge=1)

    # ---- 向量存储 / 混合检索 ----
    vector_store: Literal["in_memory", "sqlite", "pgvector"] = Field(default="in_memory")
    hybrid_retrieval_enabled: bool = Field(default=True)
    hybrid_retrieval_llm_rewrite: bool = Field(default=False)
    hybrid_dense_top_k: int = Field(default=50, ge=1)
    hybrid_sparse_top_k: int = Field(default=50, ge=1)
    hybrid_fusion_top_k: int = Field(default=30, ge=1)
    reranker_backend: Literal["lexical", "onnx", "embedding"] = Field(default="embedding")
    mock_embedding_dimension: int = Field(default=8, ge=1)
    local_embedding_dimension: int = Field(default=128, ge=8)
    vector_store_sqlite_path: str = Field(default="./data/vector_store.sqlite")

    # ---------- 工作流 ----------
    # 默认 LangGraph，`service` 仅保留为回归兜底。
    workflow_engine: Literal["service", "langgraph"] = Field(default="langgraph")
    llm_streaming_enabled: bool = Field(default=True)
    langfuse_enabled: bool = Field(default=False)
    langfuse_public_key: str | None = Field(default=None)
    langfuse_secret_key: SecretStr | None = Field(default=None)
    langfuse_host: str = Field(default="http://127.0.0.1:3001")
    workflow_chunk_size: int = Field(default=1600, ge=20)
    workflow_chunk_overlap: int = Field(default=300, ge=0)
    retrieval_top_k: int = Field(default=15, ge=1)
    retrieval_top_k_min: int = Field(default=5, ge=1)
    retrieval_top_k_ratio: float = Field(default=0.125, ge=0.01, le=1.0)
    retrieval_metrics_enabled: bool = Field(default=True)

    # ---- 内容增强管线 ----
    content_enrichment_enabled: bool = Field(default=True)
    pdf_cache_enabled: bool = Field(default=True)
    pdf_cache_dir: str = Field(default="./data/pdf_cache")
    pdf_cache_max_size_mb: int = Field(default=500, ge=50)
    pdf_cache_ttl_hours: int = Field(default=72, ge=1)
    report_parser_max_sections: int = Field(default=12, ge=1, le=50)
    table_extraction_max_tables: int = Field(default=12, ge=0, le=50)

    # ---- 分块策略 ----
    chunking_strategy: Literal["section_aware", "recursive", "fixed_window"] = Field(
        default="section_aware"
    )
    section_min_chunk_size: int = Field(default=400, ge=100)

    # ---- 内容优先化 ----
    content_prioritizer: Literal["intent_driven", "llm_driven", "none"] = Field(
        default="intent_driven"
    )
    content_max_chars: int = Field(default=120_000, ge=10_000)
    content_min_section_chars: int = Field(default=500, ge=100)
    content_prioritizer_llm_enabled: bool = Field(default=False)

    # ---- 证据摘要 ----
    grounding_snippet_max_chars: int = Field(default=300, ge=80)

    # ---- BM25 缓存 ----
    bm25_cache_max_size: int = Field(default=16, ge=1)

    # ---- 向量维度校验 ----
    vector_store_dimension_validation: Literal["strict", "warn", "ignore"] = Field(
        default="warn"
    )

    # ---------- DeepSeek LLM ----------
    # 注意：``.env`` 里给空字符串会覆盖 default。读取时一律走 ``resolved_*``。
    deepseek_api_key: SecretStr | None = Field(default=None)
    deepseek_base_url: str = Field(default=_DEFAULT_DEEPSEEK_BASE_URL)
    deepseek_model: str = Field(default=_DEFAULT_DEEPSEEK_MODEL)
    deepseek_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---------- 千帆 LLM ----------
    qianfan_api_key: SecretStr | None = Field(default=None)
    qianfan_base_url: str = Field(default=_DEFAULT_QIANFAN_BASE_URL)
    qianfan_model: str = Field(default=_DEFAULT_QIANFAN_MODEL)
    qianfan_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---------- 字段校验 ----------
    @field_validator("embedding_dimension", mode="before")
    @classmethod
    def _optional_embedding_dimension(cls, value: object) -> object:
        """空字符串视为未配置（None），避免 pydantic 报类型错。"""
        if isinstance(value, str):
            stripped = value.strip()
            return None if stripped == "" else stripped
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def _embedding_dimension_positive_when_set(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise ValueError("EMBEDDING_DIMENSION 必须 >= 1")
        return value

    @field_validator("llm_provider", "search_provider", "embedding_provider", mode="before")
    @classmethod
    def _normalize_provider_name(cls, value: str) -> str:
        return str(value).strip().lower()

    # ---------- 派生属性 ----------
    @property
    def official_url_domain_list(self) -> list[str]:
        """``OFFICIAL_URL_ALLOWED_DOMAINS`` 由逗号分隔的字符串拆成列表，便于校验。"""
        return [
            item.strip().lower()
            for item in self.official_url_allowed_domains.split(",")
            if item.strip()
        ]

    @property
    def db_scheme(self) -> str:
        """从 ``database_url`` 中提取 scheme（sqlite / postgresql 等）。

        健康检查接口暴露的是 scheme，而非完整 URL，因为 URL 中可能包含密码。
        """
        return self.database_url.split("://", 1)[0] if "://" in self.database_url else "unknown"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    # ---- 真实链路 API key 是否已配置 ----
    @property
    def has_qianfan_api_key(self) -> bool:
        return _has_secret(self.qianfan_api_key)

    @property
    def has_deepseek_api_key(self) -> bool:
        return _has_secret(self.deepseek_api_key)

    @property
    def has_baidu_ai_search_api_key(self) -> bool:
        return _has_secret(self.baidu_ai_search_api_key)

    @property
    def has_embedding_api_key(self) -> bool:
        return _has_secret(self.embedding_api_key)

    @property
    def embedding_dimension_configured(self) -> bool:
        return self.embedding_dimension is not None

    @property
    def embedding_base_url_explicitly_set(self) -> bool:
        """是否在环境变量中显式配置了非空 ``EMBEDDING_BASE_URL``。"""
        return bool((self.embedding_base_url or "").strip())

    @property
    def resolved_embedding_base_url(self) -> str | None:
        """DashScope / SiliconFlow 未配置时回退到推荐默认值；其它 provider 返回 None。"""
        provider = self.embedding_provider
        explicit = (self.embedding_base_url or "").strip()
        if provider == "dashscope":
            return explicit or _DEFAULT_DASHSCOPE_BASE_URL
        if provider == "siliconflow":
            return explicit or _DEFAULT_SILICONFLOW_BASE_URL
        return None

    @property
    def resolved_embedding_model(self) -> str | None:
        """DashScope / SiliconFlow 未配置时回退到推荐默认值；其它 provider 返回 None。"""
        provider = self.embedding_provider
        explicit = (self.embedding_model or "").strip()
        if provider == "dashscope":
            return explicit or _DEFAULT_DASHSCOPE_MODEL
        if provider == "siliconflow":
            return explicit or _DEFAULT_SILICONFLOW_MODEL
        return None

    # ---- 真实链路 URL / Model 兜底（空字符串 → default） ----
    @property
    def resolved_deepseek_base_url(self) -> str:
        return _resolve_text(self.deepseek_base_url, _DEFAULT_DEEPSEEK_BASE_URL)

    @property
    def resolved_deepseek_model(self) -> str:
        return _resolve_text(self.deepseek_model, _DEFAULT_DEEPSEEK_MODEL)

    @property
    def resolved_qianfan_base_url(self) -> str:
        return _resolve_text(self.qianfan_base_url, _DEFAULT_QIANFAN_BASE_URL)

    @property
    def resolved_qianfan_model(self) -> str:
        return _resolve_text(self.qianfan_model, _DEFAULT_QIANFAN_MODEL)

    @property
    def resolved_baidu_ai_search_endpoint(self) -> str:
        return _resolve_text(
            self.baidu_ai_search_endpoint, _DEFAULT_BAIDU_AI_SEARCH_ENDPOINT
        )

    @property
    def resolved_baidu_ai_search_model(self) -> str:
        return _resolve_text(self.baidu_ai_search_model, _DEFAULT_BAIDU_AI_SEARCH_MODEL)

    @property
    def health_embedding_model_display(self) -> str:
        """健康检查 / 脚本暴露用的模型标识，不会包含密钥。"""
        if self.embedding_provider in ("mock", "local_hashing"):
            return self.embedding_provider
        return self.resolved_embedding_model or ""

    # ---------- 运行时 ----------
    def effective(self, name: str) -> object:
        """读取配置：运行时 feature flag 覆盖优先，否则用 env/.env 值。

        惰性导入 feature_flags，避免循环依赖。
        """
        from app.core.feature_flags import resolve_flag

        return resolve_flag(name, getattr(self, name))

    def validate_runtime_provider_requirements(self) -> None:
        """缺少真实 provider key 时立刻报错，避免运行中静默回退到 mock。

        异常文案以英文为主：测试与跨语言运维脚本均按字符串匹配，不轻易调整。
        """
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
    """单例 Settings；测试中如需 override 调用 ``get_settings.cache_clear()`` 重建即可。"""
    return Settings()
