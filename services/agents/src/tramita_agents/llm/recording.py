"""Recordings of real model answers, replayed by the fake client in tests and CI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tramita_agents.llm.types import ModelClient, ModelRequest, ModelResponse, Usage


@dataclass(frozen=True)
class Recording:
    task: str
    fingerprint: str
    model: str
    text: str
    usage: Usage


def recording_path(directory: Path, task: str, fingerprint: str) -> Path:
    return directory / task / f"{fingerprint}.json"


def load_recording(directory: Path, task: str, fingerprint: str) -> Recording | None:
    path = recording_path(directory, task, fingerprint)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Recording(
        task=data["task"],
        fingerprint=data["fingerprint"],
        model=data["model"],
        text=data["text"],
        usage=Usage(**data["usage"]),
    )


def save_recording(directory: Path, recording: Recording) -> Path:
    path = recording_path(directory, recording.task, recording.fingerprint)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(recording)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


class RecordingModelClient:
    """Wraps a real client and stores every answer so the fake can replay it later."""

    def __init__(self, inner: ModelClient, directory: Path) -> None:
        self.inner = inner
        self.directory = directory

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self.inner.complete(request)
        save_recording(
            self.directory,
            Recording(
                task=request.task,
                fingerprint=request.fingerprint(),
                model=response.model,
                text=response.raw_text,
                usage=response.usage,
            ),
        )
        return response
