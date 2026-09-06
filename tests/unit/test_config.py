"""Config loading behaves as documented in
docs/architecture/02-non-functional-requirements.md 2.5: settings come from
the environment, nothing is hardcoded, and an invalid environment value is
rejected rather than silently accepted.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test AURA API")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/2")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings runtime-only kwarg

    assert settings.app_name == "Test AURA API"
    assert settings.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert settings.redis_url == "redis://h:6379/2"


def test_settings_default_environment_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings runtime-only kwarg

    assert settings.environment == "local"


def test_settings_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")  # not one of the allowed literals

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings runtime-only kwarg


def test_api_v1_prefix_is_versioned() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings runtime-only kwarg

    assert settings.api_v1_prefix == "/api/v1"
