"""Configuration and environment variables for CyberLab backend."""

from pydantic_settings import BaseSettings
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
    OPENROUTER_API_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Constants
DEFAULT_PAGINATION_LIMIT = 20
MAX_PAGINATION_LIMIT = 100
