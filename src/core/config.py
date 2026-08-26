"""Core settings module."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Unified Document Viewer"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://udv_user:udv_pass@localhost:5432/udv_db"
    SALES_SERVICE_URL: str = "http://localhost:8001"
    SERVICE_SERVICE_URL: str = "http://localhost:8002"
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 600  # seconds (10 minutes)

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
