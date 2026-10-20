from fastapi.testclient import TestClient
from pydantic import SecretStr

from tramita_agents.app import app
from tramita_agents.settings import ModelProvider, Settings, get_settings


def _client_with(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_reports_fake_provider_without_api_key() -> None:
    client = _client_with(Settings(anthropic_api_key=None))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_provider": "fake"}


def test_blank_api_key_still_selects_fake_provider() -> None:
    assert Settings(anthropic_api_key=SecretStr("  ")).model_provider is ModelProvider.FAKE


def test_api_key_selects_anthropic_provider() -> None:
    settings = Settings(anthropic_api_key=SecretStr("sk-ant-test"))

    assert settings.model_provider is ModelProvider.ANTHROPIC
