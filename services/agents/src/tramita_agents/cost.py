"""What the agents cost per claim: model calls, tokens, time and, when priced, money.

Usage: ``uv run tramita-cost-report`` (or ``make cost-report``) after ``make process``, with the
core running. It reads, for each claim of the dataset, the latest proposal's record of every
agent run (steps, tool calls, models, tokens, seconds) and writes ``evals/reports/cost.md``.

Prices are configuration, never code: ``TRAMITA_MODEL_PRICES`` maps a model id to US dollars per
million input and output tokens, as JSON, for example
``{"<model id>": {"input": <USD>, "output": <USD>}}``; take the figures from the provider's
current price list. Models without a price are reported as unpriced, never guessed. Keyless runs
use no tokens, so their cost is zero and only their time is informative.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tramita_agents.core_client import CoreClient, CoreError, role_key
from tramita_agents.settings import REPO_ROOT, Settings

REPORTS = REPO_ROOT / "evals" / "reports"
MILLION = 1_000_000
NOT_FOUND = 404


@dataclass
class AgentTotals:
    runs: int = 0
    steps: list[int] = field(default_factory=list)
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: list[float] = field(default_factory=list)
    models: set[str] = field(default_factory=set)
    providers: set[str] = field(default_factory=set)
    dollars: float = 0.0
    unpriced_tokens: int = 0


def price(
    prices: dict[str, dict[str, float]], models: Sequence[str], tokens_in: int, tokens_out: int
) -> float | None:
    """Dollars for one agent run, or None if its model has no price (or it used several)."""
    if not tokens_in and not tokens_out:
        return 0.0
    if len(models) != 1 or models[0] not in prices:
        return None
    rate = prices[models[0]]
    return (tokens_in * rate["input"] + tokens_out * rate["output"]) / MILLION


def summarise(
    proposals: Sequence[dict[str, Any]], prices: dict[str, dict[str, float]]
) -> dict[str, AgentTotals]:
    totals: dict[str, AgentTotals] = defaultdict(AgentTotals)
    for proposal in proposals:
        for name, run in ((proposal.get("model_metadata") or {}).get("agents") or {}).items():
            agent = totals[name]
            agent.runs += 1
            agent.steps.append(run.get("steps", 0))
            agent.tool_calls += len([c for c in run.get("calls", []) if c != "submit"])
            tokens_in, tokens_out = run.get("input_tokens", 0), run.get("output_tokens", 0)
            agent.input_tokens += tokens_in
            agent.output_tokens += tokens_out
            agent.seconds.append(float(run.get("seconds", 0.0)))
            agent.models |= set(run.get("models", []))
            agent.providers |= set(run.get("providers", []))
            cost = price(prices, run.get("models", []), tokens_in, tokens_out)
            if cost is None:
                agent.unpriced_tokens += tokens_in + tokens_out
            else:
                agent.dollars += cost
    return dict(totals)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)] if ordered else 0.0


def markdown(totals: dict[str, AgentTotals], claims: int) -> str:
    lines = [
        "# Cost per claim",
        "",
        f"{claims} claims with a proposal. Seconds are wall time per agent run.",
        "",
        "| Agent | Runs | Steps (mean) | Tool calls | Input tokens | Output tokens | "
        "Seconds p50 / p95 | USD | Unpriced tokens | Answered by |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, t in sorted(totals.items()):
        lines.append(
            f"| {name} | {t.runs} | {statistics.fmean(t.steps):.1f} | {t.tool_calls} | "
            f"{t.input_tokens} | {t.output_tokens} | {statistics.median(t.seconds):.3f} / "
            f"{_p95(t.seconds):.3f} | {t.dollars:.4f} | {t.unpriced_tokens} | "
            f"{', '.join(sorted(t.providers))} |"
        )
    dollars = sum(t.dollars for t in totals.values())
    unpriced = sum(t.unpriced_tokens for t in totals.values())
    lines += [
        "",
        f"Total: {dollars:.4f} USD, {dollars / claims if claims else 0:.4f} USD per claim"
        + (f"; {unpriced} tokens of models without a price are not included." if unpriced else "."),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Report what the agents cost per claim.")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "generated")
    parser.add_argument("--out", type=Path, default=REPORTS)
    args = parser.parse_args(argv)
    settings = Settings()
    if settings.tramita_api_keys is None:
        sys.exit("TRAMITA_API_KEYS is not set (see .env.example).")
    prices: dict[str, dict[str, float]] = json.loads(settings.tramita_model_prices or "{}")
    ids = [c["claim_id"] for c in json.loads((args.dataset / "claims.json").read_text("utf-8"))]
    key = role_key(settings.tramita_api_keys.get_secret_value(), "ANALYST")
    proposals: list[dict[str, Any]] = []
    with CoreClient(settings.tramita_core_url, key) as core:
        for claim_id in ids:
            try:
                found = core.claim(claim_id).get("proposals") or []
            except CoreError as error:
                if error.status != NOT_FOUND:
                    raise
                continue  # not ingested yet
            if found:
                proposals.append(found[-1])
    text = markdown(summarise(proposals, prices), len(proposals))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cost.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
