# ADR 0004: Kafka for event choreography, Temporal for per-claim orchestration

- Status: accepted
- Date: 2026-10-20

## Context

A claim moves through `claim.received → documents.extracted → analysis.completed →
decision.proposed → (review.requested →) decision.approved → payment.executed`. Some steps take
milliseconds, others take days: waiting for a policyholder to upload a missing invoice, or for a
claims handler to review a proposal. Other systems (reporting, fraud investigation, notifications)
also need to react to these facts without the claims pipeline knowing about them.

## Options considered

1. **Kafka only.** Each step is a consumer. Fan-out to other systems is natural and the log is a
   durable audit trail. Long waits, timers, compensation and "where is claim X right now" must be
   built by hand with state tables and schedulers.
2. **Temporal only.** One durable workflow per claim with timers, signals and retries built in.
   Other systems cannot subscribe to what happened without polling Temporal or adding their own
   integration.
3. **Both, each for what it is good at.**

## Decision

Option 3.

- **Kafka is the public record of facts.** Every step publishes a domain event with a correlation
  id that also travels in trace context. Each step is an independent consumer group, with retries
  using exponential backoff and a dead-letter topic per step. Anyone may subscribe.
- **Temporal owns the lifecycle of each claim.** A workflow per claim drives the steps, waits for
  signals (documents received, review completed) with timeouts, and makes the process resumable
  after crashes. Activities are idempotent and publish the corresponding Kafka events.

## Consequences

- Clear answer to "what is the state of claim X" (Temporal) and to "what happened, in order"
  (Kafka plus the core audit log).
- Two pieces of infrastructure to run. Both are single-node in Docker Compose and in the kind
  cluster; production sizing is out of scope.
- Events must be idempotent on the consumer side because Kafka delivery is at-least-once and
  Temporal activities may retry. Every event carries a stable event id used for deduplication.
