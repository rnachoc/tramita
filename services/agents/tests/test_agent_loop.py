from typing import Any

import pytest
from pydantic import BaseModel, Field

from tramita_agents.agents.loop import SUBMIT, AgentError, Tool, ToolError, run_agent
from tramita_agents.llm.fake import FakeModelClient
from tramita_agents.llm.recording import RecordingModelClient
from tramita_agents.llm.steps import StepRequest
from tramita_agents.llm.types import ModelError, Tier


class Add(BaseModel):
    a: int
    b: int


class Answer(BaseModel):
    total: int = Field(ge=0)


def _add(args: Add) -> str:
    if args.a < 0:
        raise ToolError("negative numbers are not supported")
    return str(args.a + args.b)


ADD = Tool("add", "Adds two integers.", Add, _add)


def _client(script: list[list[tuple[str, dict[str, Any]]]]) -> FakeModelClient:
    def responder(request: StepRequest) -> list[tuple[str, dict[str, Any]]]:
        return script[len(request.history)]

    return FakeModelClient(step_responders={"sum": responder})


def _run(client: FakeModelClient, max_steps: int = 5) -> Any:
    return run_agent(
        client,
        task="sum",
        tier=Tier.FAST,
        system="Add.",
        prompt="2 + 3",
        tools=[ADD],
        output=Answer,
        max_steps=max_steps,
    )


def test_tools_run_and_the_answer_is_validated() -> None:
    seen: list[StepRequest] = []
    script: list[list[tuple[str, dict[str, Any]]]] = [
        [("add", {"a": 2, "b": 3})],
        [(SUBMIT, {"total": 5})],
    ]

    def responder(request: StepRequest) -> list[tuple[str, dict[str, Any]]]:
        seen.append(request)
        return script[len(request.history)]

    run = _run(FakeModelClient(step_responders={"sum": responder}))

    assert run.output == Answer(total=5)
    assert (run.steps, run.calls, run.errors, run.providers) == (
        2,
        ["add", SUBMIT],
        0,
        {"fake:responder"},
    )
    assert seen[1].history[0].results[0].content == "5"
    assert [t.name for t in seen[0].tools] == ["add", SUBMIT]


def test_bad_input_unknown_tools_and_tool_errors_go_back_to_the_model() -> None:
    script: list[list[tuple[str, dict[str, Any]]]] = [
        [("add", {"a": "two"}), ("multiply", {}), ("add", {"a": -1, "b": 1})],
        [(SUBMIT, {"total": -5})],
        [(SUBMIT, {"total": 5})],
    ]
    seen: list[StepRequest] = []

    def responder(request: StepRequest) -> list[tuple[str, dict[str, Any]]]:
        seen.append(request)
        return script[len(request.history)]

    run = _run(FakeModelClient(step_responders={"sum": responder}))

    first = seen[1].history[0].results
    assert [r.is_error for r in first] == [True, True, True]
    assert "Invalid input for 'add'" in first[0].content
    assert first[1].content == "Unknown tool 'multiply'."
    assert first[2].content == "negative numbers are not supported"
    assert seen[2].history[1].results[0].content.startswith("Invalid answer")
    assert (run.output.total, run.errors) == (5, 4)


def test_the_step_budget_is_enforced() -> None:
    client = _client([[("add", {"a": 1, "b": 1})]] * 3)

    with pytest.raises(AgentError, match="no answer within 3 steps"):
        _run(client, max_steps=3)


def test_submit_is_reserved() -> None:
    with pytest.raises(ValueError, match="reserved"):
        run_agent(
            _client([]),
            task="sum",
            tier=Tier.FAST,
            system="",
            prompt="",
            tools=[Tool(SUBMIT, "", Add, _add)],
            output=Answer,
        )


def test_a_task_without_responder_or_recording_fails_loudly() -> None:
    with pytest.raises(ModelError, match="No recording and no responder for agent task 'sum'"):
        _run(FakeModelClient())


def test_recorded_steps_replay_without_the_model(tmp_path: Any) -> None:
    live = _client([[("add", {"a": 2, "b": 3})], [(SUBMIT, {"total": 5})]])
    recorded = _run(RecordingModelClient(live, tmp_path))  # type: ignore[arg-type]

    replayed = _run(FakeModelClient(recordings=tmp_path))

    assert replayed.output == recorded.output
    assert replayed.providers == {"fake:recording"}
