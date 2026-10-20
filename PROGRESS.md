# Progress

Single source of truth for where the project stands. Updated at the end of every phase. When
resuming work, read this file first.

## Current phase

**Phase 2: core system and rules (Java)** (next). Phases 0 and 1 are complete.

## Phase status

| Phase | Scope | Status | Release |
|---|---|---|---|
| 0 | Foundations: repo, tooling, compose stack, CI, first ADRs | done | v0.1.0 |
| 1 | Synthetic data generator | done | v0.2.0 |
| 2 | Core system and rules (Java) | pending | |
| 3 | Document reading | pending | |
| 4 | Policy search | pending | |
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

## Open issues and notes

- **MinIO replaced by RustFS** (ADR 0006): MinIO community images are no longer published.
- **Spotless runs google-java-format 1.28.0**, the newest version Spotless supports on Java 17.
- **Build environment note**: parts of this project were developed in a sandbox without access to
  Maven Central, Docker Hub or Hugging Face. Java builds, the compose stack and anything that
  downloads models were verified in GitHub Actions before reaching `main`.
