"""One durable workflow per claim (ADR 0004): analyse, then wait for what the claim needs.

The workflow owns "where is this claim now". It analyses the claim (an activity that runs the
agents and submits the proposal to the core), then, depending on the status the core answers:

- **waiting for documents**: waits for a ``documents_received`` signal and analyses again, up to
  ``documents_wait``; past it the workflow ends as ``documents_overdue`` for a person to chase;
- **pending review or under investigation**: waits for ``review_recorded`` (a claims handler
  decided), then reads the final status, up to ``review_wait``;
- **paid or rejected**: ends.

Signals come from the claim events on Kafka through the bridge and carry the event id, so a
replayed event is ignored. The workflow code is deterministic: all I/O is in activities, which
Temporal retries with backoff.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from tramita_agents.workflows.state import ClaimState

TASK_QUEUE = "claims"
ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=6,
)
FINAL = {"PAID", "REJECTED"}
AWAITING_REVIEW = {"PENDING_REVIEW", "UNDER_INVESTIGATION"}


def workflow_id(claim_id: str) -> str:
    return f"claim-{claim_id}"


@dataclass
class ClaimInput:
    claim_id: str
    documents_wait_s: int = 14 * 24 * 3600
    review_wait_s: int = 30 * 24 * 3600
    max_analyses: int = 3


@dataclass
class ClaimResult:
    claim_id: str
    outcome: str  # final status, or documents_overdue / review_overdue / too_many_rounds
    status: str
    analyses: int
    history: list[str] = field(default_factory=list)


@workflow.defn
class ClaimWorkflow:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._documents = 0
        self._reviews = 0
        self._stage = "starting"

    @workflow.signal
    def documents_received(self, event_id: str) -> None:
        if event_id not in self._seen:
            self._seen.add(event_id)
            self._documents += 1

    @workflow.signal
    def review_recorded(self, event_id: str) -> None:
        if event_id not in self._seen:
            self._seen.add(event_id)
            self._reviews += 1

    @workflow.query
    def signals_seen(self) -> int:
        return len(self._seen)

    @workflow.query
    def stage(self) -> str:
        """What the workflow is doing: analysing, waiting_documents, waiting_review, done..."""
        return self._stage

    async def _wait(self, counter: str, since: int, seconds: int) -> bool:
        """Waits for a signal counted after ``since``: one that arrived while the claim was
        being analysed counts too, so no signal is lost between the analysis and the wait."""
        try:
            await workflow.wait_condition(
                lambda: getattr(self, counter) > since, timeout=timedelta(seconds=seconds)
            )
        except TimeoutError:
            return False
        return True

    @workflow.run
    async def run(self, claim: ClaimInput) -> ClaimResult:
        analyses = 0
        history: list[str] = []
        marks = {"_documents": 0, "_reviews": 0}

        def mark() -> None:
            marks.update(_documents=self._documents, _reviews=self._reviews)

        async def analyse() -> ClaimState:
            nonlocal analyses
            analyses += 1
            mark()
            self._stage = "analysing"
            state: ClaimState = await workflow.execute_activity(
                "analyse_claim",
                claim.claim_id,
                result_type=ClaimState,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ACTIVITY_RETRY,
            )
            history.append(f"analysed:{state.status}")
            return state

        def result(outcome: str, state: ClaimState) -> ClaimResult:
            self._stage = "done"
            return ClaimResult(claim.claim_id, outcome, state.status, analyses, history)

        state = await analyse()
        while True:
            if state.status in FINAL:
                return result(state.status, state)
            if state.status == "WAITING_DOCUMENTS":
                if analyses >= claim.max_analyses:
                    return result("too_many_rounds", state)
                self._stage = "waiting_documents"
                if not await self._wait("_documents", marks["_documents"], claim.documents_wait_s):
                    return result("documents_overdue", state)
                history.append("documents_received")
                state = await analyse()
            elif state.status in AWAITING_REVIEW:
                self._stage = "waiting_review"
                if not await self._wait("_reviews", marks["_reviews"], claim.review_wait_s):
                    return result("review_overdue", state)
                history.append("review_recorded")
                mark()
                self._stage = "reading_status"
                state = await workflow.execute_activity(
                    "claim_state",
                    claim.claim_id,
                    result_type=ClaimState,
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=ACTIVITY_RETRY,
                )
                history.append(f"status:{state.status}")
            else:
                # APPROVED without payment yet, or anything new: read again shortly.
                await asyncio.sleep(timedelta(seconds=30).total_seconds())
                self._stage = "reading_status"
                state = await workflow.execute_activity(
                    "claim_state",
                    claim.claim_id,
                    result_type=ClaimState,
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=ACTIVITY_RETRY,
                )
