"""Core settings module."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Unified Document Viewer"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./search_history.db"
    SALES_SERVICE_URL: str = "http://localhost:8001"
    SERVICE_SERVICE_URL: str = "http://localhost:8002"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
