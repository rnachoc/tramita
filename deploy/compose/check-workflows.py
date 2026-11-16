"""End-to-end check of claim events and workflows against the running stack (used by CI).

Expects the core running with TRAMITA_EVENTS_ENABLED=true, the worker and the bridge running,
the given claims ingested and a workflow started for each. It approves one payment that is
waiting for review, as a claims handler would, and checks that:

* the review reaches the workflow through Kafka and the claim ends paid;
* every workflow ends, or waits for documents or a review, in line with the core's status;
* the claim events on Kafka follow the contract, keep each claim's order, carry no personal data
  and end, for the reviewed claim, with the review and the payment;
* nothing was parked in the bridge's dead-letter topic.

Prints one notice line for CI; exits 1 on the first broken expectation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx
from confluent_kafka import Consumer
from temporalio.client import Client, WorkflowExecutionStatus

from tramita_agents.core_client import role_key
from tramita_agents.events.consumer import dead_letter_topic
from tramita_agents.events.contracts import TOPIC, ClaimEvent
from tramita_agents.settings import Settings
from tramita_agents.workflows.claim import ClaimResult, ClaimWorkflow, workflow_id

DATASET = Path("data/generated")
REVIEWER = "Revisión automática de CI"
WAITING = {"WAITING_DOCUMENTS", "PENDING_REVIEW", "UNDER_INVESTIGATION"}


def fail(message: str) -> None:
    print(f"FAILED: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=workflows check::{message}")
    raise SystemExit(1)


class Core:
    def __init__(self, settings: Settings) -> None:
        self.keys = (
            settings.tramita_api_keys.get_secret_value() if settings.tramita_api_keys else ""
        )
        self.http = httpx.Client(base_url=settings.tramita_core_url, timeout=30)

    def claim(self, claim_id: str) -> dict[str, Any]:
        response = self.http.get(
            f"/api/claims/{claim_id}", headers={"X-Api-Key": role_key(self.keys, "ANALYST")}
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def payable(self, claim_id: str) -> float:
        latest = self.claim(claim_id)["proposals"][-1]
        return float(latest["payable_amount"] or 0) if latest["decision"] == "APPROVE" else 0.0

    def approve(self, claim_id: str) -> None:
        response = self.http.post(
            f"/api/claims/{claim_id}/reviews",
            headers={
                "X-Api-Key": role_key(self.keys, "REVIEWER"),
                "Idempotency-Key": f"check-{claim_id}",
            },
            json={"reviewer": REVIEWER, "action": "APPROVE", "comment": "CI"},
        )
        if response.is_error:
            fail(f"review of {claim_id} refused: {response.status_code} {response.text[:200]}")


def analysed(core: Core, claim_ids: list[str]) -> dict[str, str]:
    """Waits until no claim of the sample is still waiting for its first analysis."""
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        statuses = {c: core.claim(c)["status"] for c in claim_ids}
        if "RECEIVED" not in statuses.values():
            return statuses
        time.sleep(5)
    fail("claims still RECEIVED after 10 minutes")
    return {}


def read_topic(bootstrap: str, topic: str, seconds: float) -> list[bytes]:
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "broker.address.family": "v4",
            "group.id": f"check-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    values: list[bytes] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        message = consumer.poll(1.0)
        value = message.value() if message is not None and not message.error() else None
        if isinstance(value, bytes):
            values.append(value)
    consumer.close()
    return values


async def waiting_for_review(settings: Settings, claim_id: str, seconds: float = 300) -> bool:
    """True once the claim's workflow waits for a review; a review sent earlier would reach a
    claim the workflow has not analysed yet, and the check would prove nothing."""
    temporal = await Client.connect(settings.temporal_address)
    handle = temporal.get_workflow_handle_for(ClaimWorkflow.run, workflow_id(claim_id))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await handle.query(ClaimWorkflow.stage) == "waiting_review":
            return True
        await asyncio.sleep(2)
    return False


async def finished(settings: Settings, claim_id: str) -> ClaimResult:
    temporal = await Client.connect(settings.temporal_address)
    handle = temporal.get_workflow_handle_for(ClaimWorkflow.run, workflow_id(claim_id))
    return await asyncio.wait_for(handle.result(), timeout=180)


async def workflow_states(
    settings: Settings, claim_ids: list[str]
) -> dict[str, WorkflowExecutionStatus | None]:
    temporal = await Client.connect(settings.temporal_address)
    return {
        c: (await temporal.get_workflow_handle(workflow_id(c)).describe()).status for c in claim_ids
    }


def check_events(settings: Settings, reviewed: str) -> int:
    raw = read_topic(settings.kafka_bootstrap_servers, TOPIC, 15)
    events = [ClaimEvent.model_validate_json(value) for value in raw]
    by_claim: dict[str, list[int]] = defaultdict(list)
    for event in events:
        event.payload()  # every event follows the contract of its type
        by_claim[event.claim_id].append(int(event.event_id))
    # At least once: a replayed event may repeat, but never goes back in a claim's order.
    if unordered := [c for c, ids in by_claim.items() if ids != sorted(ids)]:
        fail(f"events out of order for {unordered[:3]}")
    holders = json.loads((DATASET / "policyholders.json").read_text("utf-8"))
    text = b"\n".join(raw).decode("utf-8")
    if REVIEWER in text or any(h["full_name"] in text for h in holders):
        fail("personal data in the claim events")
    kinds = [e.event_type for e in events if e.claim_id == reviewed]
    if kinds[-2:] != ["REVIEW_RECORDED", "PAYMENT_EXECUTED"]:
        fail(f"{reviewed} events end with {kinds[-3:]}, expected the review then the payment")
    parked = read_topic(settings.kafka_bootstrap_servers, dead_letter_topic("workflow-signals"), 5)
    if parked:
        fail(f"{len(parked)} message(s) in the bridge's dead-letter topic")
    return len(events)


def check_workflows(settings: Settings, core: Core, claim_ids: list[str]) -> None:
    for claim_id, state in asyncio.run(workflow_states(settings, claim_ids)).items():
        status = core.claim(claim_id)["status"]
        if status in WAITING and state != WorkflowExecutionStatus.RUNNING:
            fail(f"{claim_id} is {status} in the core but its workflow is {state}")
        if status in {"PAID", "REJECTED"} and state != WorkflowExecutionStatus.COMPLETED:
            fail(f"{claim_id} is {status} in the core but its workflow is {state}")


def main(claim_ids: list[str]) -> None:
    settings = Settings()
    core = Core(settings)
    statuses = analysed(core, claim_ids)
    pending = [c for c, s in statuses.items() if s == "PENDING_REVIEW" and core.payable(c) > 0]
    if not pending:
        fail("no claim with a payment waiting for review in the sample")
    reviewed = pending[0]
    amount = core.payable(reviewed)
    if not asyncio.run(waiting_for_review(settings, reviewed)):
        fail(f"the workflow of {reviewed} never reached waiting_review")
    core.approve(reviewed)
    try:
        result = asyncio.run(finished(settings, reviewed))
    except TimeoutError:
        fail(f"workflow of {reviewed} did not end within 3 minutes of the review")
    if (result.outcome, result.status) != (
        "PAID",
        "PAID",
    ) or "review_recorded" not in result.history:
        fail(f"{reviewed} ended as {result.outcome}/{result.status}: {result.history}")
    check_workflows(settings, core, claim_ids)
    count = check_events(settings, reviewed)
    counts = Counter(core.claim(c)["status"] for c in claim_ids)
    summary = (
        f"{len(claim_ids)} claims, {count} events in order, review of {reviewed} "
        f"({amount} EUR) signalled through Kafka and paid; status {dict(counts)}"
    )
    print(f"  ok   {summary}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=workflows check::{summary}")


if __name__ == "__main__":
    main(sys.argv[1].split(","))
