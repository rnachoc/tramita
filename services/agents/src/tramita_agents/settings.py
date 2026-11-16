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

    # Policy search: OpenSearch for the lexical side, pgvector in PostgreSQL for the vectors.
    opensearch_url: str = "http://localhost:9200"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "tramita"
    postgres_password: SecretStr = SecretStr("change-me-local-only")
    postgres_db: str = "tramita"
    # Local models (fastembed, ONNX on CPU), downloaded once into the cache. Chosen by measurement
    # (ADR 0012). An empty reranker turns the second stage off.
    tramita_embedding_model: str = "jinaai/jina-embeddings-v2-base-es"
    tramita_reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    tramita_models_dir: Path = REPO_ROOT / "models-cache"
    # Clauses each first-stage ranking hands over, and the most the reranker reads per query.
    tramita_search_candidates: int = 10

    # Claim events and per-claim workflows (ADRs 0004 and 0014).
    kafka_bootstrap_servers: str = "localhost:9092"
    temporal_address: str = "localhost:7233"

    @property
    def postgres_conninfo(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} dbname={self.postgres_db} "
            f"user={self.postgres_user} password={self.postgres_password.get_secret_value()}"
        )

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
