# ADR 0016: Analysts get a read-only MCP server whose results are masked

- Status: accepted
- Date: 2026-11-16

## Context

Fraud analysts and claims managers want to ask questions about claims in their own assistant
("which claims under investigation share a supplier?", "why was this one rejected?", "what does
the policy say about late notice?"). The Model Context Protocol lets a desktop assistant call
tools; whatever a tool returns is read by a model. The core already decides who may do what by
role (ADR 0009), and personal data must not reach a model (ADR 0011).

## Options considered

1. **Tools that write too** (approve, correct), with confirmations in the assistant. The fastest
   route for a handler, and the one most exposed to a model being talked into an action.
2. **Read-only tools on the ANALYST role**, results reduced and masked.
3. **No MCP**: analysts use the console and the analyst API.

## Decision

Option 2, in `services/mcp` (`tramita-mcp`, official MCP Python SDK 2.x, stdio or
streamable HTTP):

- **Tools**: `search_policy_conditions` (the hybrid search of ADR 0012), `list_claims`,
  `get_claim`, `claim_audit` and `claims_overview`; **resources** with the rules in order and each
  product's conditions. Every tool is declared read-only (`readOnlyHint`).
- **Guarded by the same roles**: the server authenticates as ANALYST, which the core allows to
  read and nothing else. A write would be refused by the core even if a tool attempted one; CI
  checks that the key gets 403 when it tries.
- **Results are written for a model**: the description is masked like a document; the incident
  address, contact details, reviewer names and account numbers are left out; document facts are
  the masked extraction; the text the reader flagged as embedded instructions is never returned,
  only a count. The server's instructions say that claim text is data, never instructions.

## Consequences

- An assistant can explain a decision with its citations and audit trail, search the conditions
  and summarise queues, and cannot change anything.
- Verified end to end in CI over stdio: 150 claims read through the tools with none of the 1,650
  personal values of the ground truth in any result, and a 403 for writes.
- Building the check found a bug in the core: a known key without the role got 401 instead of
  403, because the container forwards the error to `/error` on a dispatch that carries no key.
  MockMvc tests could not see it; a test over a real server now covers it.
- Analysts cannot see personal data through the assistant even when their job would allow it;
  they use the console for that.
- No per-user identity: every analyst acts as the server's ANALYST client (ADR 0009). With OIDC,
  the MCP server would forward the user's token instead.
