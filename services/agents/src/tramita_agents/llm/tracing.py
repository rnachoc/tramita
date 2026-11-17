"""A model client that records every call as a GenAI span and in the GenAI metrics.

Recorded: the operation, the provider, the model, the task, who answered (a real model, a
recording or a responder), tokens and duration. Never recorded: prompts, documents, answers.
"""

from __future__ import annotations

import time

from opentelemetry.trace import Span

from tramita_agents import telemetry
from tramita_agents.llm.steps import StepRequest, StepResponse
from tramita_agents.llm.types import ModelClient, ModelRequest, ModelResponse, Usage


def _provider(label: str) -> str:
    return "anthropic" if label == "anthropic" else "tramita.fake"


class TracingModelClient:
    def __init__(self, inner: ModelClient) -> None:
        self.inner = inner

    def complete(self, request: ModelRequest) -> ModelResponse:
        with telemetry.span(
            "chat",
            **{
                telemetry.OPERATION: "chat",
                "tramita.task": request.task,
                "tramita.tier": request.tier.value,
            },
        ) as current:
            started = time.perf_counter()
            response = self.inner.complete(request)
            _finish(
                current,
                task=request.task,
                model=response.model,
                label=response.provider,
                usage=response.usage,
                started=started,
            )
            return response

    def step(self, request: StepRequest) -> StepResponse:
        with telemetry.span(
            "chat",
            **{
                telemetry.OPERATION: "chat",
                "tramita.task": request.task,
                "tramita.tier": request.tier.value,
                "tramita.step": len(request.history) + 1,
            },
        ) as current:
            started = time.perf_counter()
            response = self.inner.step(request)
            current.set_attribute("tramita.tool_calls", len(response.calls))
            _finish(
                current,
                task=request.task,
                model=response.model,
                label=response.provider,
                usage=response.usage,
                started=started,
            )
            return response


def _finish(
    current: Span, *, task: str, model: str, label: str, usage: Usage, started: float
) -> None:
    provider = _provider(label)
    current.update_name(f"chat {model}")
    current.set_attribute(telemetry.PROVIDER, provider)
    current.set_attribute(telemetry.REQUEST_MODEL, model)
    current.set_attribute(telemetry.RESPONSE_MODEL, model)
    current.set_attribute("tramita.answered_by", label)
    current.set_attribute(telemetry.INPUT_TOKENS, usage.input_tokens)
    current.set_attribute(telemetry.OUTPUT_TOKENS, usage.output_tokens)
    metric = telemetry.instruments()
    common = {
        telemetry.OPERATION: "chat",
        telemetry.PROVIDER: provider,
        telemetry.REQUEST_MODEL: model,
        "tramita.task": task,
    }
    metric.operation_duration.record(time.perf_counter() - started, common)
    metric.token_usage.record(usage.input_tokens, {**common, "gen_ai.token.type": "input"})
    metric.token_usage.record(usage.output_tokens, {**common, "gen_ai.token.type": "output"})
