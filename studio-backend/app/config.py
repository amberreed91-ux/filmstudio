from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings - loaded from environment variables"""

    # App settings
    app_name: str = "Studio API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8010

    # Database settings
    storage_type: str = "sqlite"
    storage_path: str = "/Users/amberreed/Enhanced_adaptive_strategy_python/studio-backend/data"

    # Auth settings
    session_ttl_seconds: int = 86400
    demo_mode: bool = False

    # Render settings
    simulated_provider_enabled: bool = True
    max_concurrent_jobs: int = 50
    render_video_provider: str = "happyhorse"

    # Production queue settings
    production_queue_enabled: bool = True
    production_queue_worker_enabled: bool = True
    production_queue_worker_poll_interval_seconds: float = 2.0
    production_queue_lease_seconds: int = 300
    production_queue_max_batch_size: int = 5
    production_queue_global_concurrency: int = 4
    production_queue_project_concurrency: int = 2
    production_queue_provider_concurrency_json: str = "{}"
    render_poll_batch_size: int = 50
    render_poll_interval_seconds: float = 10.0
    render_recovery_hydration_limit: int = 1000

    # Provider settings (can be overridden via environment)
    higgsfield_api_key: str | None = None
    higgsfield_api_endpoint: str | None = None
    generic_api_key: str | None = None
    generic_api_endpoint: str | None = None
    runwayml_api_secret: str | None = None
    runway_api_key: str | None = None
    # Legacy environment compatibility only; the LLM fallback chain uses OpenRouter.
    groq_api_key: str | None = None
    groq_llm_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    google_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    dashscope_api_key: str | None = None
    dashscope_region: str = "intl"
    dashscope_workspace_id: str | None = None
    qwen_llm_model: str = "qwen3.7-max"
    # OpenRouter is the fallback LLM provider when Qwen/DashScope is blocked or slow.
    # Free-tier models are rate-limited, so keep this path for interactive single-shot calls.
    openrouter_llm_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_backup_llm_models: str = (
        "poolside/laguna-s-2.1:free,"
        "nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Internal timeout for the primary Qwen call before falling back to OpenRouter.
    # Kept well under the frontend's 30s AbortController timeout.
    qwen_internal_timeout_seconds: float = 12.0

    # CORS settings
    cors_origins: str = ""  # Comma-separated production origins. Empty = same-origin only.
    cors_origins_dev: str = "http://localhost:5000,http://localhost:5001,http://localhost:5173,http://127.0.0.1:5000,http://127.0.0.1:5001,http://127.0.0.1:5173"

    # Admin
    admin_token: str = ""  # Required for admin endpoints. Empty = admin endpoints disabled.

    # Rate limiting
    rate_limit_per_minute: int = 120

    # Backup
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_max_count: int = 7
    backup_dir: str = "./backups"

    # Database pool
    db_pool_size: int = 10

    # Error telemetry
    sentry_dsn: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "json" for production, "text" for development

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings
