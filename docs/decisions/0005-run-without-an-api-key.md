# ADR 0005: Everything runs without an API key, using a deterministic fake model

- Status: accepted
- Date: 2026-10-20

## Context

The repository is public and meant to be cloned and run by reviewers. Tests and CI must be fast,
free, and reproducible. Real model calls are slow, cost money, and are not deterministic, so they
cannot gate every push.

## Options considered

1. Require `ANTHROPIC_API_KEY` for anything beyond unit tests.
2. Mock the SDK ad hoc inside each test.
3. A first-class fake model provider behind the same interface as the real client, replaying
   recorded responses keyed by a hash of the request.

## Decision

Option 3. Provider selection is automatic: an empty `ANTHROPIC_API_KEY` selects the fake provider.
Recorded responses live in the repository next to the eval set. Running the evals with a real key
can refresh the recordings.

- CI always runs with the fake provider, including the eval suite and its regression gate.
- Real-model evals run in CI only when the `ANTHROPIC_API_KEY` repository secret exists.

## Consequences

- `make demo`, `make test` and `make eval` work on a fresh clone with no credentials.
- Fake-provider eval numbers measure the deterministic parts of the system (rules, fraud scoring,
  retrieval, parsing and validation) plus the recorded model behaviour. They are labelled as such
  in reports and never presented as live model quality.
- Recordings must be refreshed when prompts change; a request hash mismatch fails loudly in tests
  instead of silently returning a stale answer.
