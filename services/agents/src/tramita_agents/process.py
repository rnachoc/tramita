"""Analyses the open claims in the core and submits a proposal for each.

Usage: ``uv run tramita-process`` (or ``make process``) after ``make ingest`` and ``make index``,
with the core running. For every claim of the dataset that is still open (received or waiting
for documents) it reads the claim from the core, runs the coordinator and its agents, and submits
the proposal. The core's rules answer with the decision, the amount and the routing; nothing here
can approve or pay. Output names ids, decisions and counts, never personal data.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tramita_agents.agents.catalog import catalog
from tramita_agents.agents.context import build_context
from tramita_agents.agents.coordinator import Coordinator
from tramita_agents.agents.loop import AgentError
from tramita_agents.core_client import CoreClient, CoreError, role_key
from tramita_agents.llm.factory import build_model_client
from tramita_agents.llm.types import ModelError
from tramita_agents.responders import RESPONDERS, STEP_RESPONDERS
from tramita_agents.search.factory import build_policy_search
from tramita_agents.settings import REPO_ROOT, Settings

OPEN = {"RECEIVED", "WAITING_DOCUMENTS"}


def process_claim(
    core: CoreClient, coordinator: Coordinator, claim_id: str
) -> dict[str, Any] | None:
    view = core.claim(claim_id)
    if view["status"] not in OPEN:
        return None
    context = build_context(view, coordinator.catalog)
    plan = coordinator.plan(context, lambda: core.policy_claims(context.policy_number))
    submitted = core.submit_proposal(claim_id, plan.body, plan.idempotency_key())
    proposal = submitted["proposal"]
    return {
        "claim_id": claim_id,
        "proposed": plan.body["decision"],
        "decision": proposal["decision"],
        "routing": proposal["routing"],
        "payable": proposal["payable_amount"],
        "violations": len(proposal["violations"]),
        "status": submitted["claim_status"],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Analyse open claims and submit proposals.")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "generated")
    parser.add_argument("--claims", help="comma-separated claim ids (default: the whole dataset)")
    parser.add_argument("--limit", type=int, help="only the first N claims")
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.tramita_api_keys is None:
        sys.exit("TRAMITA_API_KEYS is not set (see .env.example).")
    ids = (
        args.claims.split(",")
        if args.claims
        else [
            c["claim_id"]
            for c in json.loads((args.dataset / "claims.json").read_text(encoding="utf-8"))
        ]
    )
    ids = ids[: args.limit] if args.limit else ids
    client = build_model_client(settings, RESPONDERS, STEP_RESPONDERS)
    search = build_policy_search(settings)
    search.check_ready()
    coordinator = Coordinator(client, search, catalog())
    key = role_key(settings.tramita_api_keys.get_secret_value(), "AGENT")
    counts: Counter[str] = Counter()
    started = time.perf_counter()
    with CoreClient(settings.tramita_core_url, key) as core:
        for claim_id in ids:
            try:
                outcome = process_claim(core, coordinator, claim_id)
            except (AgentError, ModelError, CoreError) as error:
                counts["failed"] += 1
                print(f"{claim_id}  FAILED  {type(error).__name__}: {str(error)[:200]}")
                continue
            if outcome is None:
                counts["skipped (closed)"] += 1
                continue
            counts[f"{outcome['decision']} / {outcome['routing']}"] += 1
            print(
                f"{claim_id}  proposed {outcome['proposed']:<12} rules {outcome['decision']:<12} "
                f"{outcome['routing']:<20} payable {outcome['payable']}  "
                f"violations {outcome['violations']}  -> {outcome['status']}"
            )
    print(f"\n{len(ids)} claims in {time.perf_counter() - started:.0f} s")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
    if counts["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
