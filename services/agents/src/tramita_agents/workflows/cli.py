"""Commands around the claim workflows.

- ``tramita-worker`` (``make worker``): runs the workflows and their activities.
- ``tramita-start-claims`` (``make start-claims``): starts one workflow per claim of the dataset
  that is in the core; starting a claim twice is a no-op.
- ``tramita-bridge`` (``make bridge``): consumes the claim events and signals the workflows
  (documents extracted, review recorded). Events for claims without a running workflow are
  skipped; failures are retried and then parked in the group's dead-letter topic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from temporalio.client import Client, WorkflowFailureError
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from tramita_agents.events.contracts import ClaimEvent, EventType
from tramita_agents.settings import REPO_ROOT, Settings
from tramita_agents.workflows.claim import TASK_QUEUE, ClaimInput, ClaimWorkflow, workflow_id

log = logging.getLogger(__name__)
BRIDGE_GROUP = "workflow-signals"
SIGNALS = {
    EventType.DOCUMENT_EXTRACTED: ClaimWorkflow.documents_received,
    EventType.REVIEW_RECORDED: ClaimWorkflow.review_recorded,
}


def exit_now(code: int = 0) -> None:
    """Ends a short-lived command once its work is done and its output flushed.

    The Temporal client's native (Rust) threads can race the interpreter's finalisation and abort
    the process ("PyGILState_Release ... must be current"), intermittently, after everything has
    already succeeded. Skipping finalisation avoids it; nothing is left to clean up by then.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def worker_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the claim workflow worker.")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # Only the worker loads the agents, the models and the search.
    from tramita_agents.workflows.activities import analyse_claim, claim_state  # noqa: PLC0415

    async def run() -> None:
        client = await Client.connect(Settings().temporal_address)
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            worker = Worker(
                client,
                task_queue=TASK_QUEUE,
                workflows=[ClaimWorkflow],
                activities=[analyse_claim, claim_state],
                activity_executor=pool,
                max_concurrent_activities=args.concurrency,
            )
            print(f"worker on task queue '{TASK_QUEUE}'", flush=True)
            await worker.run()

    asyncio.run(run())


def start_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Start a workflow per claim.")
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "generated")
    parser.add_argument("--claims", help="comma-separated claim ids (default: the whole dataset)")
    parser.add_argument("--documents-wait", type=int, default=ClaimInput.documents_wait_s)
    parser.add_argument("--review-wait", type=int, default=ClaimInput.review_wait_s)
    parser.add_argument("--wait", action="store_true", help="wait for every workflow to end")
    args = parser.parse_args(argv)
    ids = (
        args.claims.split(",")
        if args.claims
        else [
            c["claim_id"]
            for c in json.loads((args.dataset / "claims.json").read_text(encoding="utf-8"))
        ]
    )

    async def run() -> None:
        client = await Client.connect(Settings().temporal_address)
        started = 0
        for claim_id in ids:
            try:
                await client.start_workflow(
                    ClaimWorkflow.run,
                    ClaimInput(claim_id, args.documents_wait, args.review_wait),
                    id=workflow_id(claim_id),
                    task_queue=TASK_QUEUE,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                )
                started += 1
            except WorkflowAlreadyStartedError:
                pass
        print(f"started {started} workflow(s), {len(ids) - started} already existed")
        if args.wait:
            for claim_id in ids:
                try:
                    handle = client.get_workflow_handle_for(
                        ClaimWorkflow.run, workflow_id(claim_id)
                    )
                    result = await handle.result()
                    print(f"{claim_id}  {result.outcome:<18} {result.status:<20} {result.history}")
                except WorkflowFailureError as error:
                    print(f"{claim_id}  FAILED {error.cause}")

    asyncio.run(run())
    exit_now()


def bridge_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Signal claim workflows from claim events.")
    parser.add_argument("--idle-exit", type=float, help="stop after this many idle seconds")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Only the bridge loads the Kafka client.
    from tramita_agents.events.consumer import EventConsumer, connect  # noqa: PLC0415

    settings = Settings()
    loop = asyncio.new_event_loop()
    client = loop.run_until_complete(Client.connect(settings.temporal_address))

    def handle(event: ClaimEvent) -> None:
        kind = event.known_type()
        if kind not in SIGNALS:
            return
        handle_ = client.get_workflow_handle(workflow_id(event.claim_id))
        try:
            loop.run_until_complete(handle_.signal(SIGNALS[kind], event.event_id))
        except RPCError as error:
            if error.status != RPCStatusCode.NOT_FOUND:
                raise
            log.info("no running workflow for %s, %s skipped", event.claim_id, kind.value)
            return
        log.info("signalled %s: %s (event %s)", event.claim_id, kind.value, event.event_id)

    consumer, producer = connect(settings.kafka_bootstrap_servers, BRIDGE_GROUP)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stats = EventConsumer(consumer, producer, BRIDGE_GROUP, handle).run(stop, args.idle_exit)
    print(f"bridge stopped: {stats}")
