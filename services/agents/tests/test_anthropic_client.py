import json
from typing import Any

import anthropic
import httpx2 as httpx
import pytest
from pydantic import BaseModel

from tramita_agents.llm import ImageBlock, ModelError, ModelRequest, TextBlock, Tier
from tramita_agents.llm.anthropic_client import AnthropicModelClient
from tramita_agents.llm.steps import Exchange, StepRequest, ToolCall, ToolResult, ToolSpec


class Answer(BaseModel):
    value: int


def fake_api(
    captured: list[dict[str, Any]], *, text: str = '{"value": 5}', stop: str = "end_turn"
) -> anthropic.Anthropic:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": text}],
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 8,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 0,
                },
            },
        )

    return anthropic.Anthropic(
        api_key="test-key-not-real",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )


def request() -> ModelRequest:
    return ModelRequest(
        task="demo",
        tier=Tier.FAST,
        system="Instrucciones estables.",
        content=(TextBlock("Lee esto."), ImageBlock(b"\xff\xd8jpeg", "image/jpeg")),
        output_schema=Answer,
        max_tokens=256,
    )


MODELS = {Tier.FAST: "claude-haiku-5-5", Tier.SMART: "claude-sonnet-5-5"}


def test_sends_schema_cached_system_prompt_and_image_and_validates_the_answer() -> None:
    captured: list[dict[str, Any]] = []
    client = AnthropicModelClient(fake_api(captured), MODELS)

    response = client.complete(request())

    body = captured[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 256
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["additionalProperties"] is False
    image = body["messages"][0]["content"][1]
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/jpeg"
    assert response.parsed == Answer(value=5)
    assert response.provider == "anthropic"
    assert response.usage.cache_read_input_tokens == 100


@pytest.mark.parametrize(
    ("stop", "message"),
    [("refusal", "declined"), ("max_tokens", "raise max_tokens")],
)
def test_incomplete_answers_raise_actionable_errors(stop: str, message: str) -> None:
    client = AnthropicModelClient(fake_api([], stop=stop), MODELS)

    with pytest.raises(ModelError, match=message):
        client.complete(request())


def test_answers_outside_the_schema_are_rejected() -> None:
    client = AnthropicModelClient(fake_api([], text='{"value": "five"}'), MODELS)

    with pytest.raises(ModelError, match="does not match the schema"):
        client.complete(request())


def _tool_api(captured: list[dict[str, Any]], content: list[dict[str, Any]]) -> anthropic.Anthropic:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_tool",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": content,
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 300, "output_tokens": 20},
            },
        )

    return anthropic.Anthropic(
        api_key="test-key-not-real",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )


def _step_request() -> StepRequest:
    call = ToolCall("toolu_1", "search_conditions", {"query": "agua"})
    return StepRequest(
        task="agent.coverage",
        tier=Tier.SMART,
        system="Sistema.",
        prompt="<claim>datos</claim>",
        tools=(ToolSpec("search_conditions", "Busca.", {"type": "object", "properties": {}}),),
        history=(Exchange((call,), (ToolResult("toolu_1", "[]"),)),),
    )


def test_a_step_replays_the_conversation_and_forces_a_tool_call() -> None:
    captured: list[dict[str, Any]] = []
    use = {"type": "tool_use", "id": "toolu_2", "name": "submit", "input": {"x": 1}}
    client = AnthropicModelClient(_tool_api(captured, [use]), MODELS)

    response = client.step(_step_request())

    sent = captured[0]
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["tool_choice"] == {"type": "any"}
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["messages"][1]["content"][0]["type"] == "tool_use"
    assert sent["messages"][2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "[]",
        "is_error": False,
    }
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert response.calls == (ToolCall("toolu_2", "submit", {"x": 1}),)
    assert (response.provider, response.usage.input_tokens) == ("anthropic", 300)


def test_a_step_without_a_tool_call_fails() -> None:
    client = AnthropicModelClient(_tool_api([], [{"type": "text", "text": "hola"}]), MODELS)

    with pytest.raises(ModelError, match="without calling a tool"):
        client.step(_step_request())
