from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from the repo-root .env file."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / ".env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Rental API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5432/rental"

    secret_key: str = "dev-secret-key-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    booking_buffer_minutes: int = 15
    cors_origins: str = "http://localhost:5173"

    seed_random: int = 42

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
