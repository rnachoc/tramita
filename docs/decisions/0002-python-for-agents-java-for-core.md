# ADR 0002: Python for the agent service, Java for the core system and rules

- Status: accepted
- Date: 2026-10-20

## Context

The system has two very different halves:

- **Probabilistic work**: reading documents, searching policy terms, analysing claims with
  language models, running evaluations. This side changes weekly and leans on the ML ecosystem
  (model SDKs, embedding and reranking models, PII detection, PDF tooling, eval libraries).
- **Deterministic work**: the insurer's system of record (policies, claims, payments, audit) and
  the rules that decide what may be paid automatically. This side must be boring, strongly typed,
  transactional and easy to audit.

## Options considered

1. **Everything in Python.** One language, faster to start. Transactions, migrations and the rules
   engine would be written in a language with optional typing, and the boundary between "model
   proposes" and "code decides" would be a module boundary that is easy to bypass.
2. **Everything in Java.** Strong typing everywhere, but the ML ecosystem (Presidio, local
   embedding and reranker models, eval tooling) is thinner, and agent iteration is slower.
3. **Python for agents, Java for the core and rules**, talking over REST, Kafka and MCP.

## Decision

Option 3.

- `services/agents` (Python 3.12, FastAPI, the official Anthropic SDK, Pydantic, Temporal SDK)
  owns extraction, retrieval, the agents and the workflows.
- `services/core` (Java 17, Spring Boot 3, JPA, Flyway, PostgreSQL) owns policies, claims, the
  rules engine, fraud scoring thresholds, payments and audit.

The language boundary is also the trust boundary: the agent service can only *propose* actions
through the core's API, and the core validates every proposal against the rules before it changes
state. The model never writes to the database or executes a payment directly.

## Consequences

- The "model proposes, code decides" principle is enforced by the network, not by convention.
- Two toolchains in CI and in local development. The Makefile hides the difference.
- Shared contracts (event payloads, API schemas) must be versioned explicitly; JSON Schema files
  generated from the Pydantic models are the source of truth for event payloads.
- Spring Boot 3.5 is used as required by the brief, on Java 17. Spring Boot 4 is available; moving
  to it is a contained upgrade of `services/core` and is listed as a follow-up.
