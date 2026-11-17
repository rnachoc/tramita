"""The agent loop (ADR 0003): send the conversation, run the tools the model calls, repeat.

- **Tools are typed**: each takes a Pydantic input model. Input that does not validate, an
  unknown tool or a tool failure goes back to the model as an error result it can correct,
  never as an exception that ends the run.
- **The final answer is a tool call** (``submit``) whose input schema is the agent's output
  schema, so the answer is validated like any other tool input.
- **Limits**: a step budget and a wall-clock timeout; exceeding either fails loudly.
- **Read-only tools**: agent tools look things up and never change state. Proposals reach the
  core only through the coordinator, after the run, and the core's rules decide (ADR 0008).
- Tool results are data inside tool-result blocks, never instructions in the system prompt.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from tramita_agents import telemetry
from tramita_agents.llm.steps import Exchange, StepRequest, ToolResult, ToolSpec
from tramita_agents.llm.types import ModelClient, Tier

SUBMIT = "submit"


class AgentError(RuntimeError):
    """An agent that could not produce an answer within its limits. The message says why."""


class ToolError(RuntimeError):
    """A tool that cannot answer this input; the message goes back to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[Any], str]

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_model.model_json_schema())


@dataclass
class AgentRun[O: BaseModel]:
    output: O
    steps: int
    calls: list[str] = field(default_factory=list)  # tool names in order, for traces
    errors: int = 0  # tool results returned as errors
    providers: set[str] = field(default_factory=set)
    models: set[str] = field(default_factory=set)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


def run_agent[O: BaseModel](
    client: ModelClient,
    *,
    task: str,
    tier: Tier,
    system: str,
    prompt: str,
    tools: Sequence[Tool],
    output: type[O],
    max_steps: int = 8,
    timeout_s: float = 120.0,
) -> AgentRun[O]:
    """Runs the agent inside an ``invoke_agent`` span (GenAI conventions)."""
    with telemetry.span(
        f"invoke_agent {task}",
        **{telemetry.OPERATION: "invoke_agent", telemetry.AGENT_NAME: task},
    ) as current:
        run = _run(client, task, tier, system, prompt, tools, output, max_steps, timeout_s)
        current.set_attribute("tramita.steps", run.steps)
        current.set_attribute("tramita.tool_errors", run.errors)
        current.set_attribute(telemetry.INPUT_TOKENS, run.input_tokens)
        current.set_attribute(telemetry.OUTPUT_TOKENS, run.output_tokens)
        return run


def _run[O: BaseModel](  # noqa: PLR0917 - the arguments of run_agent, passed on
    client: ModelClient,
    task: str,
    tier: Tier,
    system: str,
    prompt: str,
    tools: Sequence[Tool],
    output: type[O],
    max_steps: int,
    timeout_s: float,
) -> AgentRun[O]:
    by_name = {t.name: t for t in tools}
    if SUBMIT in by_name:
        raise ValueError(f"'{SUBMIT}' is reserved for the final answer")
    specs = (
        *(t.spec() for t in tools),
        ToolSpec(
            SUBMIT,
            "Submit the final answer. Call it once, when you are done; it ends the task.",
            output.model_json_schema(),
        ),
    )
    started = time.monotonic()
    history: list[Exchange] = []
    run_calls: list[str] = []
    errors = 0
    providers: set[str] = set()
    models: set[str] = set()
    tokens_in = tokens_out = 0
    for step in range(1, max_steps + 1):
        if time.monotonic() - started > timeout_s:
            raise AgentError(f"{task}: no answer within {timeout_s:.0f} s ({step - 1} steps)")
        response = client.step(
            StepRequest(task, tier, system, prompt, specs, history=tuple(history))
        )
        providers.add(response.provider)
        models.add(response.model)
        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens
        results: list[ToolResult] = []
        for call in response.calls:
            run_calls.append(call.name)
            if call.name == SUBMIT:
                try:
                    answer = output.model_validate(call.input)
                except ValidationError as error:
                    results.append(ToolResult(call.call_id, f"Invalid answer: {error}", True))
                    continue
                return AgentRun(
                    output=answer,
                    steps=step,
                    calls=run_calls,
                    errors=errors,
                    providers=providers,
                    models=models,
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    seconds=round(time.monotonic() - started, 3),
                )
            results.append(_run_tool(by_name.get(call.name), call.call_id, call.name, call.input))
        errors += sum(r.is_error for r in results)
        history.append(Exchange(response.calls, tuple(results)))
    raise AgentError(f"{task}: no answer within {max_steps} steps")


def _run_tool(tool: Tool | None, call_id: str, name: str, raw: dict[str, Any]) -> ToolResult:
    with telemetry.span(
        f"execute_tool {name}",
        **{
            telemetry.OPERATION: "execute_tool",
            telemetry.TOOL_NAME: name,
            telemetry.TOOL_CALL_ID: call_id,
        },
    ) as current:
        result = _tool_result(tool, call_id, name, raw)
        current.set_attribute("tramita.tool_error", result.is_error)
        return result


def _tool_result(tool: Tool | None, call_id: str, name: str, raw: dict[str, Any]) -> ToolResult:
    if tool is None:
        return ToolResult(call_id, f"Unknown tool '{name}'.", True)
    try:
        parsed = tool.input_model.model_validate(raw)
    except ValidationError as error:
        return ToolResult(call_id, f"Invalid input for '{name}': {error}", True)
    try:
        return ToolResult(call_id, tool.run(parsed))
    except ToolError as error:
        return ToolResult(call_id, str(error), True)
