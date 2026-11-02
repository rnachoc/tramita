# Architecture

This document grows with the project. Sections marked *planned* describe the target design that
later phases implement; everything else describes the code as it is.

## Components

| Component | Path | Responsibility |
|---|---|---|
| Core service | `services/core` | System of record: policies, claims, rules engine, fraud scoring, payments, audit |
| Data generator | `data/generator` | Reproducible synthetic policies, policyholders, claims, documents and expected resolutions |
| Agent service | `services/agents` | Document reading and ingestion (*implemented*); policy search, agents, Kafka consumers, Temporal workflows (*planned*) |
| MCP server | `services/mcp` | Analyst tools over the core API, guarded by the same rules (*planned*) |
| Review console | `web/console` | Claims handler inbox, claim detail, approve / correct / reject (*planned*) |
| Evals | `services/agents/src/tramita_agents/evals`, `evals/` | Document reading evaluation with a CI gate (*implemented*); full eval set and baseline (*planned*) |

## Trust boundary

The language boundary is the trust boundary ([ADR 0002](decisions/0002-python-for-agents-java-for-core.md)),
and API roles enforce it ([ADR 0009](decisions/0009-api-keys-with-roles.md)). The agent service
authenticates as `AGENT`: it can register claims, attach documents and extractions and submit
*proposals*, but it cannot review or pay. The core checks every proposal with a pure rules engine
([ADR 0008](decisions/0008-deterministic-rules-and-fraud-scoring.md)).

```mermaid
flowchart LR
    M((Model)) -- tool calls --> A[Agent loop<br/>services/agents]
    A -- proposal<br/>role AGENT --> C[Core API<br/>services/core]
    C --> R{Rules engine}
    R -- AUTO --> P[Payment<br/>at most one per claim]
    R -- HUMAN_REVIEW or<br/>FRAUD_INVESTIGATION --> H[Claims handler<br/>role REVIEWER]
    H -- approve / correct / reject --> P
    C --> AU[(Audit trail<br/>append-only)]
```

## Rules engine

`dev.tramita.core.rules.RulesEngine` is a pure function of the policy facts, the claim facts (from
the claim form, the extracted documents and earlier claims) and the proposal. It runs these checks
in order; the first three decide regardless of the proposal:

| # | Check | Outcome when it applies |
|---|---|---|
| 1 | Incident within the policy period | Reject, `POLICY_NOT_IN_FORCE` |
| 2 | Guarantee included in the product | Reject, `NOT_INCLUDED`, must cite the "not included" clause |
| 3 | Outside the waiting period | Reject, `WAITING_PERIOD`, must cite the waiting-period clause |
| 4 | A proposed rejection relies on a catalog exclusion of that guarantee | Reject, `EXCLUSION`; otherwise violation `UNGROUNDED_REJECTION` |
| 5 | Required documents received | Request them, `MISSING_DOCUMENTS` (automatic) |
| 6 | Amounts | Pay `min(eligible, limit) - deductible`; eligible never above the documented lines plus tax |
| 7 | Notice within 7 days | Otherwise `LATE_NOTICE`: human review, cover unchanged |
| 8 | Fraud score from rule and model signals | 0.4 review, 0.7 investigation |
| 9 | Citations exist, belong to the product and include the grounding clause | Otherwise a violation |
| 10 | Routing | `AUTO` only for consistent payments up to 3,000 EUR and requests for required documents |

## Document reading

`tramita_agents.documents` turns a stored document into masked, checked facts
([ADR 0011](decisions/0011-reading-documents-with-masked-inputs.md)). Personal data never reaches
the model: born-digital PDFs are sent as masked text, scans as an image with personal data
blacked out plus the masked OCR text.

```mermaid
flowchart TD
    F[Original file<br/>S3: claims/claim/doc/file] --> K{PDF with a<br/>text layer?}
    K -- yes --> T[Text layer] --> M[Mask personal data<br/>Presidio es + Spain recognisers<br/>tokens like PERSON_1, per claim]
    K -- "no (scan)" --> O[Tesseract spa at ~300 dpi<br/>words laid out in rows] --> M
    O --> B[Black out the words<br/>that hold personal data]
    M --> Q[Model request<br/>strict output schema<br/>document quoted as data]
    B --> Q
    Q --> S[Score in code<br/>formats, arithmetic,<br/>second reading]
    M --> D[Injection detector]
    S --> P[Extraction payload<br/>masked values + confidences;<br/>typed facts only if trusted]
    D --> P
    P --> C[Core API<br/>PUT extraction]
```

- **Model client** (`tramita_agents.llm`): one interface for the Anthropic client (structured
  outputs, vision, prompt caching), a recorder, and the fake model, which replays recordings or
  answers with a labelled rule-based responder ([ADR 0010](decisions/0010-fake-model-recordings-then-rule-based-responders.md)).
  Extraction uses the fast model for text and the smart one for scans; model ids are configuration.
- **Confidence** comes from evidence, not from the model: each value is parsed, format-checked,
  cross-checked (lines, tax, total) and looked up in a second reading. Key fields below 0.6 are
  listed for review, and the typed facts the rules use are sent only above that threshold.
- **Injection**: the model reports embedded instructions in a dedicated field, a deterministic
  detector flags them independently, and nothing in the output can approve or pay.
- **Ingestion** (`make ingest`): registers each claim, stores each original, reads it, registers
  it with the type it was read as and records the extraction. All steps are idempotent.
- **Evaluation** (`make eval-extraction`): field accuracy by type and format, calibration, wrong
  facts sent to the rules, personal values reaching the model, the redacted scans or the core,
  over-masking, and planted instructions, against the generated ground truth.

## Claim lifecycle

Implemented in the core (`ClaimStatus`). Events and workflows around it are *planned*: Kafka will
carry the public record of facts and Temporal will drive each claim
([ADR 0004](decisions/0004-kafka-choreography-temporal-orchestration.md)).

```mermaid
stateDiagram-v2
    [*] --> RECEIVED: claim registered
    RECEIVED --> WAITING_DOCUMENTS: rules request a required document
    WAITING_DOCUMENTS --> WAITING_DOCUMENTS: new proposal, still missing
    RECEIVED --> PENDING_REVIEW: routing HUMAN_REVIEW
    WAITING_DOCUMENTS --> PENDING_REVIEW: routing HUMAN_REVIEW
    RECEIVED --> UNDER_INVESTIGATION: fraud score >= 0.7
    WAITING_DOCUMENTS --> UNDER_INVESTIGATION: fraud score >= 0.7
    RECEIVED --> APPROVED: routing AUTO
    WAITING_DOCUMENTS --> APPROVED: routing AUTO
    APPROVED --> PAID: payment executed
    PENDING_REVIEW --> APPROVED: handler approves or corrects
    UNDER_INVESTIGATION --> APPROVED: handler approves or corrects
    PENDING_REVIEW --> REJECTED: handler rejects
    UNDER_INVESTIGATION --> REJECTED: handler rejects
    PENDING_REVIEW --> WAITING_DOCUMENTS: handler asks for documents
    PAID --> [*]
    REJECTED --> [*]
```

Documents and extractions can change only in `RECEIVED` and `WAITING_DOCUMENTS`, so a handler
always reviews the evidence the rules checked. `PAID` and `REJECTED` are final.

## Data model

Schema `core`, migrated by Flyway (`services/core/src/main/resources/db/migration`).

```mermaid
erDiagram
    POLICYHOLDERS ||--o{ POLICIES : holds
    POLICIES ||--o{ CLAIMS : "filed under"
    CLAIMS ||--o{ CLAIM_DOCUMENTS : attaches
    CLAIMS ||--o{ PROPOSALS : "assessed by"
    PROPOSALS ||--o{ REVIEWS : "decided in"
    CLAIMS ||--o| PAYMENTS : "paid once"
    CLAIMS ||--o{ AUDIT_EVENTS : "recorded in"
```

- `proposals` stores the agents' proposal next to the full rules evaluation (JSON) and the
  decision, amount and routing the rules allowed.
- `payments.claim_id` is unique: a claim can be paid once, whatever retries or races happen.
- `audit_events` is append-only: a trigger rejects updates and deletes.
- Extracted document facts keep personal data masked; amounts, dates and invoice identifiers are
  stored in typed columns for the rules and for duplicate-invoice detection.

## Core API

JSON in snake_case. Errors are RFC 9457 problem details that name the offending field. Endpoints
that change state are idempotent: claims and documents by id, proposals and reviews by the
`Idempotency-Key` header.

| Method and path | Role | Purpose |
|---|---|---|
| `POST /api/import/policies` | ADMIN | Upsert policyholders and policies (generator format) |
| `POST /api/claims` | AGENT | Register a claim |
| `POST /api/claims/{id}/documents` | AGENT | Attach a document (file in the object store) |
| `PUT /api/claims/{id}/documents/{doc}/extraction` | AGENT | Record extracted, masked facts |
| `POST /api/claims/{id}/proposals` | AGENT | Submit a proposal; returns the rules evaluation, new status and any payment |
| `POST /api/claims/{id}/reviews` | REVIEWER | Approve, correct (within the guarantee limit) or reject |
| `GET /api/claims?status=...` | any | Inbox, default pending review and under investigation |
| `GET /api/claims/{id}` | any | Claim with documents, proposals, reviews and payment |
| `GET /api/claims/{id}/audit` | any | Audit trail |
| `GET /api/policies/{n}` and `/api/policies/{n}/claims` | any | Policy (holder reduced to id and city) and its claims |

## Local infrastructure

`make up` starts the stack in [deploy/compose/docker-compose.yml](../deploy/compose/docker-compose.yml)
and waits until every health check passes; `make smoke` then sends each service a real request.

| Service | Image | Purpose |
|---|---|---|
| postgres | `pgvector/pgvector:0.8.7-pg17-trixie` | Core data, pgvector embeddings, Temporal persistence |
| kafka | `apache/kafka:4.2.2` | Domain events, KRaft mode, no topic auto-creation |
| opensearch | `opensearchproject/opensearch:3.9.0` | Full-text search over policy clauses |
| object-store | `rustfs/rustfs:1.0.3` | S3-compatible storage for claim documents |
| temporal | `temporalio/auto-setup:1.29.7` | Durable per-claim workflows |
| temporal-ui | `temporalio/ui:2.56.0` | Workflow inspection |

## Continuous integration

Every push runs: a secret scan of the full history; Python lint, strict types and tests; the
document reading evaluation with its regression gate (fake provider); the Java build with unit,
integration (Testcontainers PostgreSQL) and cross-check tests; the compose stack with its smoke
test, the core against it, seeding, and an end-to-end ingest of a sample of claims checked through
the API and the object store; and a build of every pushed commit on its own. Test counts and eval
headlines are published as annotations, and releases are created from `docs/releases/*.md`.
