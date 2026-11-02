"""Builds the model client the configuration asks for."""

from __future__ import annotations

from collections.abc import Mapping

import anthropic

from tramita_agents.llm.anthropic_client import AnthropicModelClient
from tramita_agents.llm.fake import FakeModelClient, Responder
from tramita_agents.llm.recording import RecordingModelClient
from tramita_agents.llm.types import ModelClient, Tier
from tramita_agents.settings import ModelProvider, Settings


def build_model_client(settings: Settings, responders: Mapping[str, Responder]) -> ModelClient:
    """Anthropic when a key is configured (optionally recording), otherwise the fake."""
    if settings.model_provider is ModelProvider.FAKE:
        return FakeModelClient(settings.tramita_recordings_dir, dict(responders))
    key = settings.anthropic_api_key
    if key is None:  # unreachable: model_provider is FAKE without a key
        raise RuntimeError("Anthropic provider selected without an API key")
    real = AnthropicModelClient(
        anthropic.Anthropic(api_key=key.get_secret_value()),
        {Tier.FAST: settings.tramita_model_fast, Tier.SMART: settings.tramita_model_smart},
    )
    if settings.tramita_record_model:
        return RecordingModelClient(real, settings.tramita_recordings_dir)
    return real
