# ADR 0007: Synthetic dataset and how its ground truth is derived

- Status: accepted
- Date: 2026-10-20

## Context

Every quality number this project reports (extraction accuracy, retrieval recall, decision
accuracy, fraud precision and recall, injection resistance) is only as good as the labels it is
measured against. The repository is public, so no real policy, document or person may be used.
Labels written by hand for 150 claims would be slow to produce, inconsistent, and impossible to
regenerate when a rule changes.

## Options considered

1. **Hand-written cases.** Highest realism per case, but labels drift from the rules and the set
   cannot grow.
2. **Random generation with labels copied from the scenario that produced each claim.** Cheap, but
   a scenario label is a claim about intent, not about the facts: a "clean" claim can accidentally
   be filed 20 days after the policy started and carry an early-claim signal that its label denies.
3. **Seeded generation where the scenario only shapes the facts, and the expected resolution is
   derived from the generated facts by a reference implementation of the rules.**

## Decision

Option 3, implemented in `data/generator`:

- **One source of truth for products.** `data/policies/catalog.yaml` holds every limit, deductible,
  waiting period, exclusion, notice period, required document and fraud weight. The Spanish policy
  conditions (`data/policies/*.md`) are rendered from it with stable clause ids such as `HP-2.1`,
  and a test fails if the committed text drifts from the catalog.
- **Scenarios shape facts.** A planner picks a policy, dates, an incident and manipulations
  (missing report, unrelated invoice line, inflated total, invoice reused from another claim,
  documents dated before the incident, hidden instructions). Each incident comes with the repair
  items, stolen goods and accident circumstances that fit it, so documents only contradict the
  description when a fraud scenario plants the contradiction.
- **Labels come from facts.** `resolution.py` walks the claims in reporting order and computes fraud
  signals from what was visible at that moment (dates, round amounts, invoices already seen,
  earlier claims on the policy), then coverage, waiting period, exclusions, documents, amounts and
  routing. It is the executable specification the Java rules engine is tested against.
- **Fraud decisions are not scored on the merits.** For planted fraud the decision on the merits is
  undefined until an investigation ends, so those claims are scored on routing and signals only
  (`decision_scored: false`).
- **Late notice changes the routing, never the outcome.** Article 16 of Ley 50/1980 lets an insurer
  claim damages for late notice but not refuse cover for it alone, so late claims go to a human.
- **Rejections always reach a human.** No claim is rejected automatically, for coverage or fraud.
- **Synthetic but realistic identifiers.** NIF, CIF and IBAN values have valid check digits so PII
  detection is tested realistically; IBANs use bank code 9999, which no Spanish bank uses, and
  e-mails use the reserved `.example` domain. Every document carries a "synthetic, no validity"
  footer and the insurer, police stations and other insurers are marked as fictional.
- **Reproducible to the byte.** One seed drives Faker, the planner and the scan noise; PDFs use
  reportlab's invariant mode. Generated files are not committed (`make data` recreates them in a
  few seconds); tests assert that the same seed produces identical data and identical bytes.

The default dataset: 200 policyholders, 232 policies, 150 claims and about 230 documents (a quarter
of them scanned images), covering clean approvals, large and limit-capped payments, products that
do not include the guarantee, nine exclusions, waiting periods, late notice, missing documents,
amount adjustments, 18 planted fraud cases in four patterns, 6 decoys with a single weak signal,
and 10 prompt-injection attempts hidden in documents or claim descriptions.

## Consequences

- Changing a rule in the catalog changes the conditions text, the expected labels and (later) the
  Java rules together; tests catch any drift.
- The reference resolver could share a bug with the system under test. The risk is limited because
  the Java engine is written independently and works from *extracted* data, and disagreements are
  inspected case by case.
- Synthetic text is cleaner than real claims. Scans, inconsistent formats and hidden instructions
  add noise, but real-world performance would still need a sample of real, consented data.
