# ADR 0017: Every evaluation is compared with a committed baseline, per provider

- Status: accepted
- Date: 2026-11-16

## Context

By phase 8 the project had three evaluations, each with its own gate: document reading (ADR
0011), policy search (ADR 0012) and the agents end to end (ADR 0013). The gates were floors
chosen by hand. A floor catches a collapse but not a slow slide: a change that costs two points
of hit@5, or one more claim in the wrong queue, passes. And every number so far comes from the
keyless baselines; once a key is available, the same evaluations will produce model numbers that
must not be judged against the baselines' floors.

## Options considered

1. **Keep hand-set floors** per evaluation. Simple; blind to regressions above the floor.
2. **Compare with the previous CI run.** Automatic, but the reference moves with every merge and
   needs artefact storage; a slow slide passes one step at a time.
3. **A committed baseline**: the headline numbers of each evaluation, per provider, with the
   direction that is better and the tolerance a run may drift by, updated deliberately and
   reviewed in the diff.

## Decision

Option 3: `evals/baseline.json` and `make scorecard` (`tramita_agents.evals.baseline`).

- **Sections**: document reading (accuracy, calibration, wrong facts sent, personal values
  leaked, instructions missed, false alarms), policy search (hit@k by mode and query set), and the
  agents end to end (decision, routing, amount, exclusions, citations, unsafe settlements, fraud
  routing, fraud score agreement).
- **Tolerances**: zero for every count of harm (personal values leaked, wrong facts sent to the
  rules, claims settled without the person they needed, planted fraud settled automatically,
  decoys sent to investigation). Small elsewhere, where ONNX scores drift across CPUs (one query
  in 137 was seen to differ between runners).
- **Per provider**: each section records who produced its numbers (`fake:responder`, or the
  search models). A run by another provider is shown next to the baseline and never failed; its
  own baseline is created with `--update` when it exists.
- **Updating** is explicit (`make scorecard ARGS=--update`) and shows up in the diff of
  `evals/baseline.json`, so a worse number has to be argued in review.
- The hand-set gates stay as an absolute safety net (no leaks, no unsafe settlements, no planted
  fraud settled automatically); the scorecard adds regression detection on top.
- **New end-to-end measures** for this phase: where planted fraud ends (12 of 18 investigated,
  6 reviewed, none automatic), decoys investigated (0 of 6), fraud score equal to the expected
  (96%), and decision and routing on the claims with planted instructions.

## Consequences

- Any slide in a headline number fails CI with the metric named in the scorecard.
- The baseline is synthetic and keyless: it measures the deterministic parts and the baselines,
  not model quality. The first real-model run will need its own baseline, recorded the same way.
- An improvement does not update the baseline by itself; whoever makes it updates it on purpose.
- The scorecard covers what each CI job produces: document reading in the Python job, search and
  agents in the stack job.
