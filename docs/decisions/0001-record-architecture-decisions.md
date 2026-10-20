# ADR 0001: Record architecture decisions

- Status: accepted
- Date: 2026-10-20

## Context

Tramita combines language models with deterministic code, several storage engines and two
messaging styles. Many choices only make sense with their context, and that context is lost
quickly. Reviewers also need to see what was considered and why it was rejected.

## Options considered

1. Comments in code and commit messages only.
2. A single design document updated over time.
3. One short, immutable Architecture Decision Record per decision.

## Decision

Option 3. Each relevant decision gets a numbered file in `docs/decisions/` with four sections:
context, options considered, decision, consequences. Accepted ADRs are not rewritten; a later ADR
supersedes an earlier one and both link to each other. When a decision depends on measurements
(retrieval quality, cost, latency) the ADR includes the numbers and how to reproduce them.

## Consequences

- Decisions are reviewable in pull requests next to the code they shape.
- Superseded reasoning stays visible, which is useful when a constraint changes back.
- Writing an ADR costs a few minutes; it is only required for decisions that are expensive to
  reverse or likely to be questioned.
