# ADR 0018: One trace per claim across services, GenAI conventions, and no content in telemetry

- Status: accepted
- Date: 2026-11-17

## Context

A claim crosses the agent service (reading, search, three agents, the model) and the core (rules,
payment). When a claim is slow, expensive or wrong, the questions are where the time went, which
agent called which tool how many times, which model answered and with how many tokens, and what
the rules decided. The same telemetry must never carry personal data: a span attribute or a log
line is as much a leak as a prompt (principle 5).

## Options considered

1. **Logs only**, with a correlation id. Cheap; no timing tree, and log lines tend to grow text.
2. **A vendor LLM-observability SDK.** Rich views of prompts and answers, which is precisely the
   content this project must not export, and a second tracing system next to the core's.
3. **OpenTelemetry end to end**: GenAI semantic conventions in the agents, Micrometer with the
   OpenTelemetry bridge in the core, W3C trace context between them, OTLP to a collector, Jaeger
   for traces, Prometheus for metrics, Grafana on top. Content capture stays off.

## Decision

Option 3.

- **Spans** in the agents: `process_claim` > `analyse_claim` > `invoke_agent <agent>` >
  `chat <model>` and `execute_tool <tool>` > `policy_search`; `read_document` for each document.
  Attributes are identifiers, counts, models, tokens, outcomes and stage timings:
  `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.agent.name`, `gen_ai.tool.name`, and `tramita.*` for the
  rest. Never prompts, documents, descriptions, tool inputs or outputs; failures record the
  exception type only, since messages can quote data.
- **One trace per claim**: outgoing HTTP calls carry `traceparent`, so the core's request spans
  join the agents'. Spring Security's own spans are left out as noise.
- **Metrics**: `gen_ai.client.operation.duration` and `gen_ai.client.token.usage` with the
  conventions' bucket boundaries, `tramita.stage.duration`, `tramita.claims.analysed` by decision
  and routing, and in the core `tramita.proposals` plus request metrics labelled by URI template.
- **Collector** as a second guard: it deletes message-content attributes some instrumentations
  add. `/actuator/prometheus` is readable without a key because it holds no claim data.
- **Off by default**: nothing is exported unless `OTEL_EXPORTER_OTLP_ENDPOINT` (agents) and
  `MANAGEMENT_OTLP_TRACING_ENDPOINT` (core) are set; the stack is a compose profile
  (`make obs-up`).
- **Cost** (`make cost-report`): model calls, tokens and wall time per agent and claim, and
  dollars where `TRAMITA_MODEL_PRICES` gives a model's price; unpriced models are reported as such.

## Consequences

- Verified locally and in CI: every processed claim is one trace with both services and every
  expected span kind; none of the personal values of the ground truth (1,800 checked locally)
  appears in any span; Prometheus has the agents' and the core's metrics.
- Measuring found a bug a test would not: the SDK's default histogram buckets suit milliseconds,
  so keyless model calls read as a p95 of about 4.75 s in Grafana. Buckets now follow the
  conventions, with a test, and the CI check fails if keyless calls read as slow.
- Without content in telemetry, debugging a wrong answer means reading the proposal and its
  rationale in the core (masked), not the trace. That is the intended trade-off.
- Keyless runs have no token cost; cost numbers become meaningful with a key and configured
  prices. Model prices are not in the repository because they change.
- Batch commands stop reporting when they end: the collector keeps their series for an hour, and
  dashboards and checks read counters over a time window.
