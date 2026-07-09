from pydantic_settings import BaseSettings
from typing import Optional


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
    demo_mode: bool = True
    
    # Render settings
    simulated_provider_enabled: bool = True
    max_concurrent_jobs: int = 50
    
    # Provider settings (can be overridden via environment)
    higgsfield_api_key: Optional[str] = None
    higgsfield_api_endpoint: Optional[str] = None
    generic_api_key: Optional[str] = None
    generic_api_endpoint: Optional[str] = None
    
    # CORS settings
    cors_origins: str = "*"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings