# ADR 0008: Hard rules and fraud scoring are deterministic code; the model only proposes

- Status: accepted
- Date: 2026-10-30

## Context

A claims system pays money and can refuse it. Every payment and every refusal must be explainable
to the policyholder, to an auditor and to a regulator, and must be reproducible: the same claim
must get the same answer tomorrow. Language models are good at reading messy documents and at
judging whether facts fit an exclusion, but their output varies between runs and can be steered
by text hidden in the documents they read.

## Options considered

1. **Let the agents decide.** The coordinator agent outputs the final decision and amount. Simple,
   but a prompt injection, a hallucinated clause or an arithmetic slip becomes a payment.
2. **Model decides, code double-checks a few things.** Better, but the boundary is fuzzy and the
   checks tend to be added only after incidents.
3. **Model proposes, code decides.** The agents return a structured proposal (decision, eligible
   amount, exclusion relied on, citations, fraud signals with evidence). A pure rules engine checks
   every field against the catalog, the policy and the extracted documents, computes the amount
   itself, scores fraud with explicit weights, and decides the routing.

## Decision

Option 3, implemented in `services/core` (`dev.tramita.core.rules`):

- **Fixed order of checks**: policy in force, guarantee included, waiting period, grounded
  exclusion, required documents, amounts, notice period, fraud, citations, routing.
- **The code computes the payment**: `min(eligible, limit) - deductible`, with the eligible amount
  never above what the extracted lines plus tax support. The proposed amount is only compared.
- **Disagreement is a violation**: when the proposal contradicts a rule (approving an excluded
  guarantee, citing a clause of another product, approving with missing documents), the rule wins
  and the violation is stored and shown to the handler. Any violation sends the claim to a human.
- **Fraud is scored, not judged, by the model**: the fraud agent returns signals with a type,
  quoted evidence and a confidence; signals without evidence are discarded. The rules add the
  signals they can establish themselves (early claim, frequent claims, duplicate invoice,
  documents dated before the incident, round amounts). Signals are merged by type and combined
  with a noisy-OR, `1 - prod(1 - weight x confidence)`, with weights and thresholds read from the
  catalog: 0.4 sends the claim to review, 0.7 to investigation.
- **Asymmetric automation**: only low-risk outcomes run without a person: paying a covered,
  consistent claim of up to 3,000 EUR, and asking for a document the catalog requires. Rejections,
  adjustments, late notices, large payments, information the catalog does not require and any
  fraud suspicion always reach a claims handler. No claim is rejected for fraud by the system.
- **Trust boundary in the network**: the agent service authenticates with the AGENT role, which can
  submit proposals but cannot review or pay (ADR 0009).

## Consequences

- The engine is a pure function with no I/O, unit-tested case by case, and cross-checked against
  the data generator's independent reference resolver: both must agree on decision, routing,
  amount and fraud score for all 150 claims of the eval set.
- Model quality changes how often the agents and the rules agree, never what is paid without a
  person.
- Weights are expert-set, not learned. With real labelled outcomes they could be fitted (for
  example with logistic regression on the same signals) while keeping the scorer explainable.
- New rules require Java changes and tests; that friction is intended for rules that move money.
