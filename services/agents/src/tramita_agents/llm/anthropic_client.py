"""Model client backed by the Anthropic Messages API.

- Structured outputs: the request's Pydantic schema is sent as ``output_config.format`` (adapted
  with :func:`anthropic.transform_schema`), and the answer is validated again locally.
- Vision: image blocks are sent as base64 sources.
- Prompt caching: the system prompt carries a cache breakpoint, so long, stable instructions
  (and, later, policy conditions) are billed at the cache-read rate after the first call.
"""

from __future__ import annotations

import time

import anthropic
from anthropic.types import (
    ImageBlockParam,
    MessageParam,
    OutputConfigParam,
    TextBlockParam,
)
from pydantic import ValidationError

from tramita_agents.llm.types import (
    ImageBlock,
    ModelError,
    ModelRequest,
    ModelResponse,
    TextBlock,
    Tier,
    Usage,
)


class AnthropicModelClient:
    def __init__(self, client: anthropic.Anthropic, models: dict[Tier, str]) -> None:
        self.client = client
        self.models = models

    @staticmethod
    def _content(request: ModelRequest) -> list[TextBlockParam | ImageBlockParam]:
        blocks: list[TextBlockParam | ImageBlockParam] = []
        for block in request.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageBlock):
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": block.media_type,  # type: ignore[typeddict-item]
                            "data": block.base64(),
                        },
                    }
                )
        return blocks

    def complete(self, request: ModelRequest) -> ModelResponse:
        model = self.models[request.tier]
        started = time.perf_counter()
        try:
            system: list[TextBlockParam] = [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ]
            messages: list[MessageParam] = [{"role": "user", "content": self._content(request)}]
            output_config: OutputConfigParam = {
                "format": {
                    "type": "json_schema",
                    "schema": anthropic.transform_schema(request.output_schema),
                }
            }
            message = self.client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                system=system,
                messages=messages,
                output_config=output_config,
            )
        except anthropic.APIError as error:
            raise ModelError(f"Anthropic API call for '{request.task}' failed: {error}") from error

        if message.stop_reason == "refusal":
            raise ModelError(f"The model declined the '{request.task}' request.")
        if message.stop_reason == "max_tokens":
            raise ModelError(
                f"The '{request.task}' answer was cut at {request.max_tokens} tokens; raise max_tokens."
            )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            parsed = request.output_schema.model_validate_json(text)
        except ValidationError as error:
            raise ModelError(
                f"Answer for '{request.task}' does not match the schema: {error}"
            ) from error
        usage = message.usage
        return ModelResponse(
            parsed=parsed,
            raw_text=text,
            model=message.model,
            provider="anthropic",
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
