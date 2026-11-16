"""Activities of the claim workflow: the I/O, retried by Temporal.

``analyse_claim`` is idempotent: it only proposes for a claim that is still open, and the core
deduplicates a proposal it has already received (same body, same idempotency key). The models,
the search and the clients are built once per worker process.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from temporalio import activity

from tramita_agents.agents.catalog import catalog
from tramita_agents.agents.coordinator import Coordinator
from tramita_agents.core_client import CoreClient, role_key
from tramita_agents.llm.factory import build_model_client
from tramita_agents.responders import RESPONDERS, STEP_RESPONDERS
from tramita_agents.search.factory import build_policy_search
from tramita_agents.settings import Settings


@dataclass
class ClaimState:
    status: str
    decision: str | None = None
    routing: str | None = None


@lru_cache
def _runtime() -> tuple[Coordinator, CoreClient]:
    settings = Settings()
    if settings.tramita_api_keys is None:
        raise RuntimeError("TRAMITA_API_KEYS is not set (see .env.example).")
    search = build_policy_search(settings)
    search.check_ready()
    coordinator = Coordinator(
        build_model_client(settings, RESPONDERS, STEP_RESPONDERS), search, catalog()
    )
    key = role_key(settings.tramita_api_keys.get_secret_value(), "AGENT")
    return coordinator, CoreClient(settings.tramita_core_url, key)


@activity.defn
def analyse_claim(claim_id: str) -> ClaimState:
    from tramita_agents.process import process_claim  # noqa: PLC0415 - avoids an import cycle

    coordinator, core = _runtime()
    outcome = process_claim(core, coordinator, claim_id)
    if outcome is None:  # already decided: report where it stands
        return claim_state(claim_id)
    return ClaimState(outcome["status"], outcome["decision"], outcome["routing"])


@activity.defn
def claim_state(claim_id: str) -> ClaimState:
    _, core = _runtime()
    view = core.claim(claim_id)
    proposals = view.get("proposals") or []
    latest = proposals[-1] if proposals else {}
    return ClaimState(view["status"], latest.get("decision"), latest.get("routing"))
