# ADR 0013: Agents judge, code coordinates, and agents can only escalate

- Status: accepted
- Date: 2026-11-16

## Context

Phase 5 turns read documents and searchable conditions into a proposal for each claim. The
core's rules already decide everything that can be computed (ADR 0008): policy in force,
guarantee included, waiting period, documents, amounts, notice, rule fraud signals and routing.
What they cannot compute are the judgements that need reading: whether the declared facts fall
under an exclusion, whether a repair line belongs to the incident, whether the documents describe
the incident that was declared. If an agent misses one of those, the rules have nothing to catch
it with: a claim with an excluded cause, or with an unrelated line, looks like any other.

The loop must run without a key (ADR 0005, ADR 0010), keep personal data away from the model
(ADR 0011), and leave the decision to the rules.

## Options considered

**Who coordinates.**

1. A coordinator agent that calls specialist agents as tools and writes the proposal.
2. A coordinator in code that asks specialist agents only for the judgements.

**How an agent returns its answer.** Structured output on a final turn, or a `submit` tool whose
input schema is the output schema.

**What an agent may do about uncertainty.** Nothing (the proposal stands), lower its confidence
in a score the rules weigh, or ask for a person.

## Decision

- **Coordinator in code** (option 2). The order of the questions is the rules' order and is not
  a matter of judgement; a model choosing it adds variance and cost and a new way to skip a
  step. Code checks the facts that need no reading, runs the coverage agent (exclusions), the
  damage agent (which lines belong) and the fraud agent (signals with quoted evidence), and
  composes the proposal. The grounding citation comes from the clause index the core uses; the
  agents' own citations are kept when they exist in the product.
- **Agent loop on the plain SDK** (ADR 0003): typed read-only tools, a `submit` tool for the
  answer (validated like any tool input), errors returned to the model, a step budget and a
  timeout. The coverage agent's tools search only the claim's product.
- **Code does the arithmetic and the checks**: eligible amount from the lines the damage agent
  keeps, signals dropped unless their evidence appears word for word in the claim data,
  exclusion codes outside the guarantee's list ignored.
- **Agents can only escalate.** Each agent may return a `review_request`; documents with embedded
  instructions add one too. A proposal with any request is routed to a person by the core
  (`REVIEW_REQUESTED`). Nothing an agent returns can lower a routing.
- **Keyless baselines always escalate.** The step responders (ADR 0010) search with the
  description and propose an exclusion only when the best clause is the guarantee's exclusions
  clause, take repair lines at face value and report no reading-based fraud signal. Nothing has
  read the claim, so they ask for a person every time.

## Measurements

`make process` then `make eval-agents` on the 150 generated claims, keyless (`fake:responder`),
against the expected resolutions (ADR 0007):

| Measure | Baseline without escalation | With escalation (chosen) |
|---|---|---|
| Decision correct (scored on the merits) | 96.2% | 96.2% |
| Exclusions found / proposed wrongly | 10 of 14 / 0 | 10 of 14 / 0 |
| Agents' own citations include the grounding clause | 73.8% | 74.6% |
| Rule violations | 1 (`NO_AMOUNTS`) | 1 (`NO_AMOUNTS`) |
| Routing as expected | 89.3% | 58.0% |
| **Settled automatically but should not be** | **10** | **0** |

The ten were six claims with an unrelated repair line the baseline accepted and four exclusions
it missed, all paid automatically under 3,000 EUR. With escalation, the 57 claims that would
have been paid automatically go to a person instead; requests for required documents stay
automatic (14).

## Consequences

- The keyless pipeline is safe but not useful as automation: without a model, a person sees
  every payment. That is the honest reading of "nobody read this claim".
- With a model, automation depends on the model not asking for review when it should, which the
  same evaluation measures; the gate allows no unsafe automatic settlement in any mode.
- No numbers with a real model yet: CI has no key. `TRAMITA_RECORD_MODEL=true` with a key records
  every step, and the evaluation reports the provider.
- The baselines do not detect unrelated lines or a mismatch between documents and incident; the
  six fraud claims that rely on such a mismatch reach review rather than investigation.
- The review reasons travel in the proposal and the rationale; the core stores the reason code
  in its evaluation but not the text in a column of its own.
