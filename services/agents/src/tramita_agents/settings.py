"""Runtime configuration, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProvider(StrEnum):
    """Which model backend the agents talk to."""

    FAKE = "fake"
    ANTHROPIC = "anthropic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    # Model identifiers are configuration, never code: they change over time.
    tramita_model_fast: str = "claude-haiku-5-5"
    tramita_model_smart: str = "claude-sonnet-5-5"

    @property
    def model_provider(self) -> ModelProvider:
        """Without an API key the whole system runs on the deterministic fake model."""
        key = self.anthropic_api_key
        if key is None or not key.get_secret_value().strip():
            return ModelProvider.FAKE
        return ModelProvider.ANTHROPIC


@lru_cache
def get_settings() -> Settings:
    return Settings()
