import uuid
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from tramita_agents.workflows.activities import ClaimState
from tramita_agents.workflows.claim import ClaimInput, ClaimResult, ClaimWorkflow

DAY = 24 * 3600


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


def _activities(
    analyses: list[str], states: list[str]
) -> tuple[Callable[[str], ClaimState], Callable[[str], ClaimState]]:
    @activity.defn(name="analyse_claim")
    def analyse_claim(claim_id: str) -> ClaimState:
        return ClaimState(analyses.pop(0))

    @activity.defn(name="claim_state")
    def claim_state(claim_id: str) -> ClaimState:
        return ClaimState(states.pop(0))

    return analyse_claim, claim_state


async def _run(
    client: Client,
    analyses: list[str],
    states: list[str],
    drive: Callable[[WorkflowHandle[ClaimWorkflow, ClaimResult]], object] | None = None,
    **options: int,
) -> ClaimResult:
    queue = f"test-{uuid.uuid4()}"
    with ThreadPoolExecutor(2) as pool:
        async with Worker(
            client,
            task_queue=queue,
            workflows=[ClaimWorkflow],
            activities=list(_activities(analyses, states)),
            activity_executor=pool,
        ):
            handle = await client.start_workflow(
                ClaimWorkflow.run,
                ClaimInput("CL-1", **options),
                id=f"claim-test-{uuid.uuid4()}",
                task_queue=queue,
            )
            if drive:
                await drive(handle)  # type: ignore[misc]
            return await handle.result()


async def test_a_claim_settled_automatically_ends_after_one_analysis(
    env: WorkflowEnvironment,
) -> None:
    result = await _run(env.client, ["PAID"], [])

    assert (result.outcome, result.analyses, result.history) == ("PAID", 1, ["analysed:PAID"])


async def test_a_review_signal_resumes_the_claim_and_reads_its_final_status(
    env: WorkflowEnvironment,
) -> None:
    async def review(handle: WorkflowHandle[ClaimWorkflow, ClaimResult]) -> None:
        await env.sleep(5 * DAY)
        await handle.signal(ClaimWorkflow.review_recorded, "event-9")
        await handle.signal(ClaimWorkflow.review_recorded, "event-9")  # replayed by Kafka

    result = await _run(env.client, ["PENDING_REVIEW"], ["PAID"], review)

    assert result.outcome == "PAID"
    assert result.history == ["analysed:PENDING_REVIEW", "review_recorded", "status:PAID"]


async def test_missing_documents_are_waited_for_and_the_claim_analysed_again(
    env: WorkflowEnvironment,
) -> None:
    async def documents(handle: WorkflowHandle[ClaimWorkflow, ClaimResult]) -> None:
        await env.sleep(3 * DAY)
        await handle.signal(ClaimWorkflow.documents_received, "event-4")

    result = await _run(env.client, ["WAITING_DOCUMENTS", "PAID"], [], documents)

    assert result.outcome == "PAID"
    assert result.analyses == 2


async def test_documents_that_never_arrive_end_as_overdue(env: WorkflowEnvironment) -> None:
    result = await _run(env.client, ["WAITING_DOCUMENTS"], [], documents_wait_s=14 * DAY)

    assert (result.outcome, result.status) == ("documents_overdue", "WAITING_DOCUMENTS")


async def test_a_review_that_never_comes_ends_as_overdue(env: WorkflowEnvironment) -> None:
    result = await _run(env.client, ["UNDER_INVESTIGATION"], [], review_wait_s=30 * DAY)

    assert result.outcome == "review_overdue"


async def test_a_signal_during_the_analysis_is_not_lost(env: WorkflowEnvironment) -> None:
    async def early(handle: WorkflowHandle[ClaimWorkflow, ClaimResult]) -> None:
        await handle.signal(ClaimWorkflow.documents_received, "event-1")

    result = await _run(
        env.client, ["WAITING_DOCUMENTS", "REJECTED"], [], early, documents_wait_s=60
    )

    assert (result.outcome, result.analyses) == ("REJECTED", 2)
