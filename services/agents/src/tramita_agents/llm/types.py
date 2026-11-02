"""Provider-neutral request and response types for structured model calls."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class Tier(StrEnum):
    """Which model a task needs. The concrete model ids live in configuration."""

    FAST = "fast"  # classification, extraction, simple checks
    SMART = "smart"  # reasoning over coverage, damages and fraud


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class ImageBlock:
    data: bytes
    media_type: str  # "image/jpeg" or "image/png"

    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")


@dataclass(frozen=True)
class ModelRequest:
    """One user turn whose answer must validate against ``output_schema``.

    ``task`` names the job (for example ``document_extraction``). It selects the fake
    responder, labels traces and metrics, and keeps recordings of different tasks apart.
    """

    task: str
    tier: Tier
    system: str
    content: tuple[TextBlock | ImageBlock, ...]
    output_schema: type[BaseModel]
    max_tokens: int = 4096

    def fingerprint(self) -> str:
        """Stable hash of everything that influences the answer, used to key recordings."""
        blocks = [
            {"text": b.text}
            if isinstance(b, TextBlock)
            else {"image": hashlib.sha256(b.data).hexdigest(), "media_type": b.media_type}
            for b in self.content
        ]
        canonical = json.dumps(
            {
                "task": self.task,
                "tier": self.tier.value,
                "system": self.system,
                "content": blocks,
                "schema": self.output_schema.model_json_schema(),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    """A validated structured answer and how it was produced."""

    parsed: BaseModel
    raw_text: str
    model: str
    provider: str  # "anthropic", "fake:recording" or "fake:responder"
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0


class ModelError(RuntimeError):
    """A model call that cannot produce a valid answer. The message says why and what to do."""


class ModelClient(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...
