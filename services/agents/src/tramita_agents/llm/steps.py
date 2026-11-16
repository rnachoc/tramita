"""One step of an agent: the model sees the conversation so far and answers with tool calls.

Agents never get free text back: every turn must call a tool (``tool_choice: any``), and the final
answer is itself a tool call whose input schema is the agent's output schema (see
:mod:`tramita_agents.agents.loop`). Conversations hold masked text only, never images.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tramita_agents.llm.types import Tier, Usage


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Exchange:
    """The model's tool calls in one turn and what the tools answered."""

    calls: tuple[ToolCall, ...]
    results: tuple[ToolResult, ...]


@dataclass(frozen=True)
class StepRequest:
    task: str
    tier: Tier
    system: str
    prompt: str
    tools: tuple[ToolSpec, ...]
    history: tuple[Exchange, ...] = ()
    max_tokens: int = 4096

    def fingerprint(self) -> str:
        """Stable hash of everything that influences the next step, used to key recordings."""
        canonical = json.dumps(
            {
                "task": self.task,
                "tier": self.tier.value,
                "system": self.system,
                "prompt": self.prompt,
                "tools": [[t.name, t.description, t.input_schema] for t in self.tools],
                "history": [
                    [
                        [[c.call_id, c.name, c.input] for c in e.calls],
                        [[r.call_id, r.content, r.is_error] for r in e.results],
                    ]
                    for e in self.history
                ],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StepResponse:
    calls: tuple[ToolCall, ...]
    model: str
    provider: str  # "anthropic", "fake:recording" or "fake:responder"
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0


StepResponder = Callable[[StepRequest], list[tuple[str, dict[str, Any]]]]
"""Deterministic stand-in for the model in one agent step: the tool calls to make, by name."""


def calls_to_json(calls: tuple[ToolCall, ...]) -> str:
    return json.dumps(
        [{"id": c.call_id, "name": c.name, "input": c.input} for c in calls], ensure_ascii=False
    )


def calls_from_json(text: str) -> tuple[ToolCall, ...]:
    return tuple(ToolCall(c["id"], c["name"], c["input"]) for c in json.loads(text))
