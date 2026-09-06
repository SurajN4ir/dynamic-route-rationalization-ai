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


@lru_cache
def get_settings() -> Settings:
    return Settings()
