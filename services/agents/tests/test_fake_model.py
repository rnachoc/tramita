from pathlib import Path

import pytest
from pydantic import BaseModel

from tramita_agents.llm import ImageBlock, ModelError, ModelRequest, TextBlock, Tier, Usage
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.recording import (
    Recording,
    RecordingModelClient,
    load_recording,
    save_recording,
)


class Answer(BaseModel):
    value: int


def request(text: str = "hola", task: str = "demo") -> ModelRequest:
    return ModelRequest(
        task=task,
        tier=Tier.FAST,
        system="Eres un asistente.",
        content=(TextBlock(text),),
        output_schema=Answer,
    )


def test_fingerprint_is_stable_and_sensitive_to_every_input() -> None:
    base = request()
    assert base.fingerprint() == request().fingerprint()
    assert base.fingerprint() != request(text="adiós").fingerprint()
    assert base.fingerprint() != request(task="other").fingerprint()
    with_image = ModelRequest(
        task="demo",
        tier=Tier.FAST,
        system="Eres un asistente.",
        content=(ImageBlock(b"\x89PNG", "image/png"),),
        output_schema=Answer,
    )
    assert with_image.fingerprint() != base.fingerprint()


def test_responder_answers_are_validated_and_labelled() -> None:
    fake = FakeModelClient(responders={"demo": lambda r: '{"value": 7}'})

    response = fake.complete(request())

    assert response.parsed == Answer(value=7)
    assert response.provider == "fake:responder"


def test_recordings_take_precedence_over_responders(tmp_path: Path) -> None:
    req = request()
    save_recording(
        tmp_path,
        Recording("demo", req.fingerprint(), "claude-haiku-5-5", '{"value": 42}', Usage(10, 2)),
    )
    fake = FakeModelClient(tmp_path, responders={"demo": lambda r: '{"value": 7}'})

    response = fake.complete(req)

    assert response.parsed == Answer(value=42)
    assert response.provider == "fake:recording"
    assert response.model == "claude-haiku-5-5"
    assert response.usage.input_tokens == 10


def test_missing_recording_and_responder_fails_loudly() -> None:
    with pytest.raises(ModelError, match="No recording and no responder for task 'demo'"):
        FakeModelClient().complete(request())


def test_answers_that_do_not_match_the_schema_are_rejected() -> None:
    fake = FakeModelClient(responders={"demo": lambda r: '{"value": "many"}'})

    with pytest.raises(ModelError, match="does not match the schema"):
        fake.complete(request())


def test_recording_client_stores_what_the_inner_client_answered(tmp_path: Path) -> None:
    inner = FakeModelClient(responders={"demo": lambda r: '{"value": 3}'})
    recorder = RecordingModelClient(inner, tmp_path)
    req = request()

    recorder.complete(req)

    stored = load_recording(tmp_path, "demo", req.fingerprint())
    assert stored is not None
    assert stored.text == '{"value": 3}'
    assert FakeModelClient(tmp_path).complete(req).provider == "fake:recording"
