from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings loaded from the repo-root .env file."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env.example", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Rental API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5432/rental"

    secret_key: str = "dev-secret-key-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    booking_buffer_minutes: int = 30
    cors_origins: str = "http://localhost:5173"
    max_active_bookings_per_user: int = 10

    seed_random: int = 42

    # --- Правила бронирования ---
    max_rental_days: int = 90
    booking_horizon_days: int = 90
    client_cancel_deadline_hours: int = 2
    client_late_cancel_percent: float = 5.0
    owner_late_cancel_hours: int = 24
    owner_compensation_percent: float = 10.0
    technical_cancel_minutes: int = 20
    late_return_grace_minutes: int = 15
    no_show_percent_of_duration: int = 25
    no_show_min_minutes: int = 15
    no_show_max_minutes: int = 120
    dispute_sla_hours: int = 48
    no_show_scheduler_enabled: bool = True
    no_show_scheduler_interval_seconds: int = 300

    dispute_max_active: int = 3
    dispute_max_per_30d: int = 10
    dispute_rate_per_hour: int = 5
    dispute_min_description: int = 50
    dispute_premoderation_ratio: float = 0.5
    dispute_premoderation_min_total: int = 5
    dispute_premoderation_days: int = 30
    appeal_window_hours: int = 24

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
