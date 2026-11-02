from pathlib import Path

from pydantic import SecretStr

from tramita_agents.llm.anthropic_client import AnthropicModelClient
from tramita_agents.llm.factory import build_model_client
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.recording import RecordingModelClient
from tramita_agents.llm.types import Tier
from tramita_agents.settings import Settings


def test_without_a_key_the_fake_is_used_with_the_recordings_and_responders(tmp_path: Path) -> None:
    settings = Settings(anthropic_api_key=None, tramita_recordings_dir=tmp_path)

    client = build_model_client(settings, {"demo": lambda r: "{}"})

    assert isinstance(client, FakeModelClient)
    assert client.recordings == tmp_path
    assert set(client.responders) == {"demo"}


def test_with_a_key_the_configured_models_are_used() -> None:
    settings = Settings(anthropic_api_key=SecretStr("sk-ant-test"), tramita_model_fast="m-fast")

    client = build_model_client(settings, {})

    assert isinstance(client, AnthropicModelClient)
    assert client.models[Tier.FAST] == "m-fast"


def test_recording_can_be_switched_on(tmp_path: Path) -> None:
    settings = Settings(
        anthropic_api_key=SecretStr("sk-ant-test"),
        tramita_record_model=True,
        tramita_recordings_dir=tmp_path,
    )

    client = build_model_client(settings, {})

    assert isinstance(client, RecordingModelClient)
    assert client.directory == tmp_path
