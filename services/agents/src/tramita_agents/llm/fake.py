"""Deterministic stand-in for the model, so everything runs without an API key (ADR 0005).

Resolution order for every request:

1. A **recording** of a real model answer to the same request (same fingerprint), stored by
   :class:`~tramita_agents.llm.recording.RecordingModelClient` when running with a key.
2. A **responder** registered for the request's task: deterministic code that produces an answer
   from the request itself (for example, rule-based extraction from the document text). Results
   from responders are labelled as such in every report; they are a baseline, not model quality.
3. Otherwise the call fails with a message naming the task and fingerprint. Nothing is invented.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from tramita_agents.llm.recording import load_recording
from tramita_agents.llm.types import ModelError, ModelRequest, ModelResponse, Usage

Responder = Callable[[ModelRequest], str]
"""Returns the answer as JSON text that must validate against the request's schema."""

FAKE_MODEL = "fake"


class FakeModelClient:
    def __init__(
        self, recordings: Path | None = None, responders: dict[str, Responder] | None = None
    ) -> None:
        self.recordings = recordings
        self.responders = dict(responders or {})

    def register(self, task: str, responder: Responder) -> None:
        self.responders[task] = responder

    def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        fingerprint = request.fingerprint()
        recording = (
            load_recording(self.recordings, request.task, fingerprint) if self.recordings else None
        )
        if recording is not None:
            text, model, provider, usage = (
                recording.text,
                recording.model,
                "fake:recording",
                recording.usage,
            )
        elif request.task in self.responders:
            text, model, provider, usage = (
                self.responders[request.task](request),
                FAKE_MODEL,
                "fake:responder",
                Usage(),
            )
        else:
            raise ModelError(
                f"No recording and no responder for task '{request.task}' "
                f"(fingerprint {fingerprint[:12]}). Run once with ANTHROPIC_API_KEY to record it."
            )
        try:
            parsed = request.output_schema.model_validate_json(text)
        except ValidationError as error:
            raise ModelError(
                f"{provider} answer for '{request.task}' does not match the schema: {error}"
            ) from error
        return ModelResponse(
            parsed=parsed,
            raw_text=text,
            model=model,
            provider=provider,
            usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
