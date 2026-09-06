"""Application configuration.

Single source of runtime config, read from environment variables / a local
.env file (see docs/architecture/02-non-functional-requirements.md 2.5 and
docs/architecture/15-deployment-architecture.md 15.5). Never hardcode a
secret here - defaults exist only for frictionless local development and
are not fit for anything beyond that.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AURA API"
    app_version: str = "0.1.0"
    environment: Literal["local", "ci", "demo"] = "local"

    api_v1_prefix: str = "/api/v1"

    log_level: str = "INFO"
    log_json: bool = True

    # Async SQLAlchemy URL (asyncpg driver). Compose sets this to the
    # `postgres` service hostname; this default targets a locally-running
    # Postgres for running the API outside Docker.
    database_url: str = "postgresql+asyncpg://aura:aura_dev_password@localhost:5432/aura"
    database_pool_size: int = 5
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # Telemetry ingestion (TASK-204) - see docs/architecture/TASK204_DESIGN.md
    # §5/§6 for why each default was chosen.
    telemetry_max_speed_mps: float = 40.0
    telemetry_max_clock_skew_past_s: int = 30
    telemetry_max_clock_skew_future_s: int = 5
    telemetry_stale_threshold_s: int = 15
    telemetry_offline_threshold_s: int = 300
    telemetry_segment_search_radius_m: float = 50.0
    telemetry_state_cache_ttl_s: int = 1800


@lru_cache
def get_settings() -> Settings:
    return Settings()
