# Progress

Single source of truth for where the project stands. Updated at the end of every phase. When
resuming work, read this file first.

## Current phase

**Phase 11: Kubernetes** (next). Phases 0 to 10 are complete.

## Phase status

| Phase | Scope | Status | Release |
|---|---|---|---|
| 0 | Foundations: repo, tooling, compose stack, CI, first ADRs | done | v0.1.0 |
| 1 | Synthetic data generator | done | v0.2.0 |
| 2 | Core system and rules (Java) | done | v0.3.0 |
| 3 | Document reading | done | v0.4.0 |
| 4 | Policy search | done | v0.5.0 |
| 5 | Agents | done | v0.6.0 |
| 6 | Events and long-running processes | done | v0.7.0 |
| 7 | Review console (Angular) | done | v0.8.0 |
| 8 | MCP server | done | v0.9.0 |
| 9 | Full evaluation | done | v0.10.0 |
| 10 | Observability and cost | done | v0.11.0 |
| 11 | Kubernetes | pending | |
| 12 | Wrap-up | pending | |

## Phase 0: done

- Repository hygiene: MIT license, ignore rules, editor config, `.env.example` with local-only
  placeholders.
- Secret scanning: gitleaks as a pre-commit hook and over the full history in CI.
- `uv` workspace with shared ruff and strict mypy configuration; FastAPI agent service skeleton
  that selects the fake model provider when no API key is set.
- Spring Boot 3.5 / Java 17 core service skeleton with actuator health and Spotless formatting.
- Docker Compose stack, all with health checks: PostgreSQL 17 + pgvector, Kafka 4.2 (KRaft),
  OpenSearch 3.9, RustFS (S3), Temporal 1.29 and its UI.
- Makefile entry points (`make up`, `make test`, `make lint`, `make secrets`, ...).
- CI on every push: secret scan, Python lint/types/tests, Java build/tests, compose smoke test.
  Failing steps publish their last output lines as annotations.
- ADRs 0001 to 0006.

## Phase 1: done

- Product catalog (`data/policies/catalog.yaml`) as the single source of truth for limits,
  deductibles, waiting periods, exclusions, required documents and fraud weights.
- Seven Spanish policy condition documents rendered from the catalog with stable clause ids, plus
  a structured clause index (`data/policies/clauses.json`). A test fails on drift.
- Seeded generator (`make data`): 200 policyholders, 232 policies, 150 claims, about 230 documents
  (PDF invoices, estimates, police reports, accident reports; a quarter as scanned JPEGs).
- Expected resolution per claim derived from the facts (ADR 0007): decision, payable amount,
  routing, reasons, clause citations, missing documents, fraud signals and score.
- Coverage of the brief: planted fraud (18, four patterns), decoys (6), out of cover (10 not
  included + 14 exclusions + 6 waiting periods), late notice (10), incomplete documentation (14),
  amount adjustments (12) and hidden prompt injections (10).
- 24 generator tests: determinism to the byte, label invariants, identifier check digits, policy
  text consistency.

## Phase 2: done

- Core service (Java 17, Spring Boot 3.5): policies, claims, documents with masked extractions,
  proposals, reviews, payments and audit, in schema `core` with Flyway migrations V1 to V5.
- Pure rules engine with a fixed order of checks; the code computes every payment, rule/proposal
  disagreements become violations that force human review, citations must exist, belong to the
  product and include the grounding clause (ADR 0008).
- Deterministic fraud scorer: rule signals (early claim, frequent claims, duplicate invoice,
  documents before the incident, round amounts) plus model signals with evidence, noisy-OR with
  catalog weights.
- API keys with roles AGENT, REVIEWER, ANALYST, ADMIN (ADR 0009); idempotent claims, documents,
  proposals (Idempotency-Key) and reviews; one payment per claim enforced by the database;
  append-only audit trail enforced by a trigger; problem-detail errors that name the field to fix.
- Tests: 41 Java (rules unit tests, fraud scorer, API keys, 9 integration tests against
  PostgreSQL with Testcontainers, and a cross-check where the Java engine agrees with the Python
  reference resolver on all 150 claims) and 31 Python.
- CI now also: exercises every compose service with a real request, starts the core jar against
  the stack and seeds it from `.env.example`, builds every pushed commit on its own, and publishes
  test counts.
- `make seed`, `make core-run`, `make smoke`.

## Phase 3: done

- Model client (`tramita_agents.llm`): Anthropic structured outputs, vision and prompt caching;
  recorder; fake model that replays recordings, then answers with labelled rule-based responders
  (ADR 0010).
- Masking with Presidio (Spanish) plus Spain-specific and OCR-tolerant recognisers; stable
  pseudonyms per claim. Scans: Tesseract at ~300 dpi, rows rebuilt across table columns, personal
  data blacked out in the image (ADR 0011).
- Strict extraction schema; confidence computed in code from formats, arithmetic and a second
  reading; facts below 0.6 withheld from the rules and listed for review.
- Injection: documents quoted as data, model reports instructions, deterministic detector.
- `make ingest` (S3 + core) and `make eval-extraction` with a CI gate; CI ingests a sample of
  claims end to end against the stack.
- Baseline results (233 documents): 100% classification and key fields; 0 wrong facts sent;
  0 personal values leaked to the model, the redacted scans or the core; 0 rule values over-masked;
  injections found in 3 of 3 PDFs, 0 of 3 scans, no false alarms.
- Tests: 141 Python, 41 Java.

## Phase 4: done

- Hybrid policy search (`tramita_agents.search`), one clause per entry, always within the
  policy's product: BM25 in OpenSearch (Spanish light stemmer, accent folding), local embeddings
  (`jinaai/jina-embeddings-v2-base-es`) in pgvector (schema `policy_search`, keyed by model),
  reciprocal rank fusion of ten candidates per stage, and a local cross-encoder
  (`BAAI/bge-reranker-v2-m3`, int8). Models run on CPU through fastembed; no API key.
- Queries are masked like documents before any backend or model; each hit keeps its rank at
  every stage. The search refuses to run on a missing or stale index.
- `make index`, `make eval-retrieval`, and `POST /policy-search` on the agent service.
- Evaluation on 432 queries: 72 claim descriptions answered by the clause that grounds the
  expected decision, 295 everyday questions, 65 keyword searches. Hit@5: BM25 60.4%, vectors
  90.7%, hybrid 87.7%, hybrid + reranker 91.9% (hit@1 73.6%, 1.5 s per query on CPU). Each first
  stage has a blind spot (BM25 on everyday words, vectors on literal terms); the reranked hybrid
  has none. Four embedding models, two rerankers and two candidate counts compared (ADR 0012).
- CI indexes the conditions and gates hit@5 per mode and query set.
- Tests: 174 Python, 41 Java.

## Phase 5: done

- Agent loop on the plain SDK (ADR 0003): typed read-only tools, the answer as a `submit` tool
  validated against the output schema, tool errors returned to the model, step budget and
  timeout. Every model client can take tool-use steps; the fake replays recorded steps or asks a
  deterministic step responder (ADR 0010).
- Coordinator in code (ADR 0013): guarantee included, waiting period and required documents
  checked without a model; coverage agent (exclusions, searching the product's conditions),
  damage agent (which lines belong; code computes the amount) and fraud agent (signals with
  quoted evidence; code drops unquoted ones). Grounding citations from the clause index.
- Agents can only escalate: review requests from any agent, or from documents with embedded
  instructions, make the core route to a person (`REVIEW_REQUESTED`, new in the core).
- `make process`, `make eval-agents`; CI ingests and analyses every claim and gates the outcome.
- Keyless end to end on 150 claims: decision 96.2%, exclusions 10 of 14 with none wrong, 1 rule
  violation, 0 automatic settlements that a person should have seen (10 before escalation).
- Tests: 197 Python, 43 Java.

## Phase 6: done

- Transactional outbox over the audit trail (ADR 0014): a relay in the core publishes every
  committed change, in order, to `tramita.claim-events` keyed by claim, moves its cursor only
  after the broker acknowledges, waits on sequence gaps from in-flight transactions and skips
  old ones. Only listed fields leave the core. Off unless `TRAMITA_EVENTS_ENABLED=true`.
- Event contract in Pydantic, `docs/events/claim-event.schema.json` generated and checked for
  drift in Python and against the relay in Java.
- Consumers with manual commits, in-place retries with capped backoff and a dead-letter topic
  per group; contract breaks go straight to it.
- `ClaimWorkflow` per claim on Temporal: analyse, wait for documents or a review with deadlines,
  end when paid or rejected; signals carry event ids (replays ignored, none lost during an
  analysis). Bridge from Kafka to signals. `make worker`, `make bridge`, `make start-claims`.
- Tests: 214 Python (workflows on Temporal's time-skipping server), 51 Java (relay against real
  PostgreSQL and Kafka). CI runs the loop on the stack: twenty workflows, a review through the
  API reaches the workflow through Kafka and the claim ends paid; events in order, no personal
  data, empty dead-letter topic.

## Phase 7: done

- `web/console`: Angular 22 review console in Spanish. Inbox by queue; claim page with facts,
  the rules' evaluation, cited clauses with text, documents as read, fraud signals, the agents'
  review requests and the audit trail; approve, correct or reject with the core's checks
  mirrored and an idempotency key per submission.
- Served by an unprivileged nginx that proxies `/api` to the core and adds the REVIEWER key; the
  browser holds no credential (ADR 0015). Strict CSP, no inline script.
- Tests: 12 Vitest unit tests; 3 Playwright end-to-end tests in CI against the console container
  and the core (a payment approved through the console ends paid; no key in any request or
  file; a rejection without a comment is refused before sending).
- The agents now keep their review requests in the proposal's metadata, shown to the handler.

## Phase 8: done

- `services/mcp` (`tramita-mcp`, official MCP SDK 2.x): read-only tools for analysts (policy
  search, claim list, one claim, audit trail, overview by status) and resources (the rules, each
  product's conditions). It reads with the ANALYST key; every tool is declared read-only (ADR 0016).
- Results are masked for the model: description masked, no address, contacts, reviewer names,
  account numbers or flagged instruction text.
- CI over stdio: 150 claims read with 0 of 1,650 personal values in any result; the server's key
  gets 403 when it tries to write.
- Fixed in the core on the way: a known key without the role got 401 instead of 403 behind a real
  servlet container (error dispatch); covered by a new test over HTTP.
- The intermittent crash on exit seen in phase 6 was caught with the fault handler: the Temporal
  client's native threads raced interpreter shutdown (`PyGILState_Release`). Short-lived
  commands that use Temporal now end without finalisation once their work is done and flushed.
- Tests: 221 Python, 53 Java, 12 console unit and 3 end-to-end.

## Phase 9: done

- End-to-end evaluation extended with fraud (where planted fraud ends: 12 of 18 investigated,
  6 reviewed, 0 automatic; 0 of 6 decoys investigated; fraud score equal to the expected in 96%)
  and planted instructions (decision 90%, no unsafe settlement). The gate fails on any planted
  fraud settled automatically.
- `evals/baseline.json` and `make scorecard`: every headline number of document reading, policy
  search and the agents, per provider, with direction and tolerance (zero for counts of harm).
  Runs of another provider are reported, never failed. CI writes a scorecard after each
  evaluation (ADR 0017).
- Tests: 229 Python, 53 Java, 12 console unit and 3 end-to-end.

## Phase 10: done

- OpenTelemetry in the agents with the GenAI conventions: spans per claim, agent, model call
  (provider, model, tokens), tool call, search stage and document; metrics for model duration and
  tokens (conventions' buckets), stage durations and claims by routing. No text in any span.
- Core: Micrometer tracing with the OpenTelemetry bridge, joined to the agents' traces by
  `traceparent`; Prometheus metrics including `tramita.proposals` by decision and routing.
- Compose profile `observability`: OTel collector (drops content attributes), Jaeger, Prometheus
  and a provisioned Grafana dashboard (`make obs-up`).
- `make cost-report`: calls, tokens, time and, for priced models, dollars per agent and claim.
- Verified: every processed claim is one trace with agents and core; 0 of 1,800 personal values
  in the traces; histogram buckets fixed after Grafana showed keyless calls at ~4.75 s (ADR 0018).
  CI processes the claims with telemetry on and checks Jaeger and Prometheus.
- Tests: 235 Python, 54 Java.

## Open issues and notes

- **No real cost numbers**: keyless runs use no tokens, and model prices are configuration.

- **The baseline is keyless**: it measures the deterministic parts and the rule-based baselines;
  a real-model run will need its own baseline, recorded with `make scorecard ARGS=--update`.

- **MCP users share one identity** (the server's ANALYST client); per-user tokens need OIDC.

- **Reviewers are not individually authenticated** (ADR 0009, ADR 0015): whoever reaches the
  console reviews as the console. Production needs OIDC and per-user sessions.

- **One relay per core**: several core instances would need a lock on the relay row.
- **Overdue workflows end** (`documents_overdue`, `review_overdue`) for a person to chase; there
  are no reminders or escalations yet.

- **No real-model numbers for the agents.** The keyless baselines read nothing, so they escalate
  every payment; automation rates with Claude are unmeasured until a key is available.
- **The baselines miss unrelated repair lines and document/incident mismatches**; with
  escalation those claims reach a person, but the six mismatch frauds go to review rather than
  investigation.

- **Policy search queries are synthetic** and written by the project's author; the numbers
  compare options, they do not predict accuracy on real policyholder text (ADR 0012).
- **Reranking costs about 1.5 s per query on CPU**. Fine for background claim processing; an
  interactive tool would want a GPU or a smaller reranker.
- **ONNX scores vary slightly across CPUs**: one query of 137 differed between two CI runs on
  different runners. Gate floors leave room for it.

- **Small print in scans** is invisible to Tesseract: planted instructions there are left to the
  vision model, and personal data printed that small would not be redacted.
- **No real-model numbers yet**: CI has no `ANTHROPIC_API_KEY`; with one, `make eval-extraction`
  reports Claude's results and `TRAMITA_RECORD_MODEL=true` stores recordings.

- **MinIO replaced by RustFS** (ADR 0006): MinIO community images are no longer published.
- **Spotless runs google-java-format 1.28.0**, the newest version Spotless supports on Java 17.
- **Reviewers are not individually authenticated** (ADR 0009): the console has a REVIEWER key and
  the reviewer's name travels in the request. Production would use OIDC.
- **Fraud weights are expert-set** in the catalog, not learned (ADR 0008).
- **Build environment note**: parts of this project were developed in a sandbox without access to
  Maven Central, Docker Hub or Hugging Face. Java builds, the compose stack and anything that
  downloads models were verified in GitHub Actions before reaching `main`.
