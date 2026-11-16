# Working rules for Tramita

Read [PROGRESS.md](PROGRESS.md) first: it says which phase is current and what is done.
[docs/architecture.md](docs/architecture.md) and the ADRs in [docs/decisions](docs/decisions)
explain why the code is the way it is.

## Principles

- **The model proposes, the code decides.** Hard rules live in code, with tests. A model output
  never writes to the database, moves money or decides a routing on its own.
- **Personal data is masked** before it reaches any model, trace or log.
- **Everything runs without `ANTHROPIC_API_KEY`**, using the fake model: recordings first, then
  labelled rule-based responders ([ADR 0005](docs/decisions/0005-run-without-an-api-key.md),
  [ADR 0010](docs/decisions/0010-fake-model-recordings-then-rule-based-responders.md)).
- **No secrets in the repository.** Local values go in `.env` (ignored); `.env.example` only holds
  local-development placeholders.
- **All data is synthetic.**

## Language

- Code, documentation, ADRs and commit messages in English.
- The insurer's documents (policy conditions, claim documents) in Spanish.
- Talking to the maintainer: Spanish, without long dashes.

## Commits

- One commit per implementation, in English, following
  [Conventional Commits](https://www.conventionalcommits.org/).
- Before each commit: `make lint` and the tests the change affects.
- Work on `main`, push every few commits and check that CI ends green.
- Test against the real stack (`make up`) before pushing anything that talks to it.

## Decisions

- Every relevant decision gets an ADR in `docs/decisions` (context, options, decision,
  consequences). Decisions that depend on measurements include the numbers and how to reproduce
  them.

## Closing a phase

1. Update [PROGRESS.md](PROGRESS.md) and the [README](README.md).
2. Write `docs/releases/vX.Y.Z.md`; the release workflow creates the tag and the release.
3. Write an interview note in Spanish in `notes/NN-fase-N-....md`. `notes/` is ignored: never
   commit it.

## Verification

- Verify everything; assume nothing. Measure with data, not only with green tests.
- Document limitations honestly, in PROGRESS.md and in the ADRs.
