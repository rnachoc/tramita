# ADR 0010: The fake model replays recordings first, then answers with labelled rule-based responders

- Status: accepted (refines ADR 0005)
- Date: 2026-11-02

## Context

ADR 0005 decided that everything runs without an API key through a fake model that replays
recorded answers keyed by a hash of the request. Building document reading showed two gaps:

- A recording only exists for a request that was made once with a key. Any document not in the
  recorded set, or any change to a prompt, a schema or the masking, changes the hash, and the
  pipeline cannot run at all on a fresh clone or in CI until someone records again with a key.
- The repository has no key in CI today, so there would be no recordings for a long time.

## Options considered

1. **Recordings only, fail on a miss** (ADR 0005 as written). Honest, but the keyless pipeline
   stops at the first document, so the ingest command, the end-to-end check and the evaluation
   cannot run in CI.
2. **Return a canned answer on a miss.** Keeps things running but produces made-up data that
   looks like model output.
3. **Recordings first, then a deterministic responder per task, else fail.** A responder is
   ordinary code that answers from the request itself: for `document.read`, regular expressions
   over the masked text it was given. Its answers are real computations, not invented, and every
   response says which path produced it.

## Decision

Option 3, in `tramita_agents.llm.fake.FakeModelClient`:

1. A recording with the request's fingerprint (task, tier, system prompt, content including image
   hashes, output schema) is replayed and labelled `fake:recording`.
2. Otherwise, if a responder is registered for the task (`tramita_agents.responders`), its answer
   is validated against the same schema the real model must follow and labelled
   `fake:responder`.
3. Otherwise the call fails, naming the task and fingerprint.

`RecordingModelClient` stores real answers when `TRAMITA_RECORD_MODEL=true` and a key is set.
The rule-based document reader sees exactly what the model would see (masked text, and for
scans the masked OCR; it ignores the image), so it is also a baseline for the model.

## Consequences

- `make ingest`, `make eval-extraction` and the CI end-to-end check run on a fresh clone without
  credentials.
- Reports state who answered. Numbers from `fake:responder` are the baseline's, never presented as
  model quality. On scans the responder reads the same OCR that scores its answers, so its
  confidences are less informative than a vision model's, and the report says so.
- A responder can hide a stale recording: after a prompt change, keyless runs silently move from
  recordings to the responder. The provider label in every report makes the move visible.
- Responders are code to maintain. Only tasks that can be answered honestly by deterministic code
  get one; the others keep failing loudly without a recording.
