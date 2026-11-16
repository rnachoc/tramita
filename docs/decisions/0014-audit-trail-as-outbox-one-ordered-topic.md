# ADR 0014: The audit trail is the outbox, published to one ordered topic of claim events

- Status: accepted (refines [ADR 0004](0004-kafka-choreography-temporal-orchestration.md))
- Date: 2026-11-16

## Context

ADR 0004 made Kafka the public record of facts and Temporal the owner of each claim's
lifecycle. Two questions were left open: how the core publishes a fact without ever publishing
one that did not commit (or losing one that did), and how the topics are laid out.

The core already writes an append-only audit event in the same transaction as every state change
(claim received, document received or extracted, proposal evaluated, review recorded, payment
executed). The agents and the workflows must react to some of them: a document that arrives for a
claim waiting for documents, a review a claims handler records.

## Options considered

**Publishing.**

1. Send to Kafka from the service methods. A crash between commit and send loses the event; a
   send before a rollback publishes a fact that never happened.
2. A dedicated outbox table written next to each change, plus a relay.
3. Change data capture (Debezium) on the audit table. Exact, but one more stateful service.
4. The existing audit trail as the outbox, plus a relay in the core.

**Topics.** One topic per step (`claim.received`, `decision.proposed`, ...) or one topic of
claim events keyed by claim.

## Decision

- **Option 4.** The audit trail already has every committed change, in the same transaction, and
  only those. A relay in the core (`EventRelay`, on with `TRAMITA_EVENTS_ENABLED=true`) reads the
  events after its cursor, publishes them and only then moves the cursor (`core.event_relay`).
  Delivery is at least once; `event_id` is unique and increasing, and consumers deduplicate.
- **Sequence gaps.** Ids are taken before commit, so a lower id can commit after a higher one. A
  gap before an event younger than 30 s stops the batch until the transaction that may fill it
  ends; an older gap is a rolled-back insert and is skipped.
- **One topic, `tramita.claim-events`, keyed by claim id** (three partitions). A claim's events
  stay in order across types, which per-type topics cannot promise; consumers filter by
  `event_type`. Topics are created explicitly (the broker does not auto-create).
- **No personal data.** Only listed fields per type leave the core: not the reviewer's name, not
  the masked account, never a description. Events of reference data imports are not published.
- **Contract.** Pydantic models generate `docs/events/claim-event.schema.json`; a Python test
  fails on drift and a core test checks the relay against the same file. Unknown event types are
  skipped by consumers, so the core can add types first.
- **Consumers** commit offsets only after handling, retry in place with capped exponential
  backoff (keeping the order) and park what still fails, or breaks the contract, in
  `tramita.claim-events.dlt.<group>` with the error in the headers.
- **Workflows.** Ingestion is followed by one `ClaimWorkflow` per claim (`make start-claims`).
  The bridge (`make bridge`, group `workflow-signals`) turns `DOCUMENT_EXTRACTED` and
  `REVIEW_RECORDED` into workflow signals carrying the event id. Waits have deadlines (14 days for
  documents, 30 for a review) after which the workflow ends as overdue for a person to chase.

## Consequences

- No event without a commit and no commit without an event, with no new write path in the core
  and no new infrastructure.
- Events are published within about half a second of the change; the relay is a single writer
  per core instance. Several core instances would need a lock on the relay row (a
  `SELECT ... FOR UPDATE` on `event_relay`); one instance is what this project runs.
- A transaction longer than the gap grace could have its event published out of order with a
  later one. Transactions in the core are short; the grace is configurable.
- The workflow module imports nothing heavy (activities are called by name), so Temporal's
  sandbox re-imports stay cheap, and a `stage` query says what each workflow waits for.
- One CI run hit a segmentation fault as a short-lived command exited, after its work was done;
  it did not recur in reruns nor in a local reproduction on the runner's OS. The CI step runs
  with `PYTHONFAULTHANDLER` so a recurrence shows where it happens.
- Verified end to end in CI: 20 claims through the workflows, a review approved through the API
  travels core, audit, relay, Kafka, bridge and Temporal, and the workflow ends paid; events stay
  in order per claim, carry no personal data, and the dead-letter topic stays empty.
