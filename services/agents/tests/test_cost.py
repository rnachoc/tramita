from typing import Any

import pytest

from tramita_agents.cost import markdown, price, summarise

PRICES = {"model-a": {"input": 1.0, "output": 5.0}}


def _proposal(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"model_metadata": {"agents": agents}}


def _run(model: str, tokens_in: int, tokens_out: int, seconds: float = 1.0) -> dict[str, Any]:
    return {
        "steps": 2,
        "calls": ["search_conditions", "submit"],
        "models": [model],
        "providers": ["anthropic"],
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "seconds": seconds,
    }


def test_a_priced_run_costs_its_tokens_at_the_configured_rates() -> None:
    assert price(PRICES, ["model-a"], 2_000_000, 100_000) == pytest.approx(2.5)


def test_runs_without_tokens_cost_nothing_and_unknown_models_are_not_guessed() -> None:
    assert price({}, ["fake"], 0, 0) == 0.0
    assert price(PRICES, ["model-b"], 10, 10) is None
    assert price(PRICES, ["model-a", "model-b"], 10, 10) is None


def test_the_report_adds_priced_runs_and_counts_unpriced_tokens_apart() -> None:
    proposals = [
        _proposal({"coverage": _run("model-a", 1_000_000, 0), "damage": _run("model-b", 50, 50)}),
        _proposal({"coverage": _run("model-a", 1_000_000, 0, seconds=3.0)}),
    ]

    totals = summarise(proposals, PRICES)
    report = markdown(totals, claims=2)

    assert totals["coverage"].runs == 2
    assert totals["coverage"].tool_calls == 2
    assert totals["coverage"].dollars == pytest.approx(2.0)
    assert totals["damage"].unpriced_tokens == 100
    assert "Total: 2.0000 USD, 1.0000 USD per claim; 100 tokens" in report
