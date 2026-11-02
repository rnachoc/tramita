"""Runtime configuration, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


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
    # Recorded real answers, replayed by the fake model (ADR 0005).
    tramita_recordings_dir: Path = REPO_ROOT / "evals" / "recordings"
    # With a key, also store every real answer so keyless runs can replay it.
    tramita_record_model: bool = False

    # S3-compatible document store (RustFS locally, ADR 0006).
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "tramita"
    s3_secret_key: SecretStr = SecretStr("change-me-local-only")
    s3_bucket: str = "claim-documents"

    # Core system API; the agents call it with the AGENT entry of TRAMITA_API_KEYS.
    tramita_core_url: str = "http://localhost:8080"
    tramita_api_keys: SecretStr | None = None

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
