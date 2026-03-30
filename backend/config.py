"""Configuration and environment variables for CyberLab backend."""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "sqlite:///./cyberlab.db"
    
    # Application
    APP_NAME: str = "CyberLab"
    DEBUG: bool = False
    VERSION: str = "0.1.0"
    
    # AI
    OPENROUTER_API_KEY: str

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Grinder
    GRINDER_UPLOAD_DIR: str = "./drop"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

    @field_validator("OPENROUTER_API_KEY")
    @classmethod
    def validate_openrouter_api_key(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("OPENROUTER_API_KEY must be set in backend/.env")
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Constants
DEFAULT_PAGINATION_LIMIT = 20
MAX_PAGINATION_LIMIT = 100
