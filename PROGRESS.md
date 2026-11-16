# Progress

Single source of truth for where the project stands. Updated at the end of every phase. When
resuming work, read this file first.

## Current phase

**Phase 5: agents** (next). Phases 0 to 4 are complete.

## Phase status

| Phase | Scope | Status | Release |
|---|---|---|---|
| 0 | Foundations: repo, tooling, compose stack, CI, first ADRs | done | v0.1.0 |
| 1 | Synthetic data generator | done | v0.2.0 |
| 2 | Core system and rules (Java) | done | v0.3.0 |
| 3 | Document reading | done | v0.4.0 |
| 4 | Policy search | done | v0.5.0 |
| 5 | Agents | pending | |
| 6 | Events and long-running processes | pending | |
| 7 | Review console (Angular) | pending | |
| 8 | MCP server | pending | |
| 9 | Full evaluation | pending | |
| 10 | Observability and cost | pending | |
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

## Open issues and notes

- **Policy search queries are synthetic** and written by the project's author; the numbers
  compare options, they do not predict accuracy on real policyholder text (ADR 0012).
- **Reranking costs about 1.5 s per query on CPU**. Fine for background claim processing; an
  interactive tool would want a GPU or a smaller reranker.
- **ONNX scores vary slightly across CPUs**: one query of 137 differed between a desktop and the
  CI runner. Gate floors leave room for it.

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
