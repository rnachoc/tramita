# ADR 0009: API keys with roles for service-to-service calls

- Status: accepted
- Date: 2026-10-30

## Context

The core API is called by the agent service, the review console, the MCP server and a seeding
script. What each caller may do is the trust boundary of the system: the agents must be able to
propose and never to approve or pay. The project must run locally with one command, without an
identity provider.

## Options considered

1. **No authentication inside the cluster.** Simplest, but then the boundary between "propose" and
   "decide" is only a convention.
2. **OAuth 2 / OIDC with an identity provider** (Keycloak or a cloud IdP). The right choice in
   production, but it adds a stateful service, realm configuration and token handling to every
   local run and every test.
3. **Static API keys mapped to roles**, configured through one environment variable, with Spring
   Security enforcing role-based access per endpoint.

## Decision

Option 3 for this project, designed so it can be swapped for option 2:

- Roles: `AGENT` (register claims and documents, submit proposals), `REVIEWER` (approve, correct or
  reject), `ANALYST` (read only) and `ADMIN` (import reference data).
- Keys are passed in `X-Api-Key`, compared in constant time, must be at least 16 characters, are
  never logged, and have no default: with `TRAMITA_API_KEYS` unset every call is rejected.
- The audit trail records the authenticated client and role of every change. The reviewer's own
  name travels in the review request.

## Consequences

- The trust boundary is enforced and tested: an integration test checks that the agent key gets
  403 when it tries to review.
- Individual reviewers are not authenticated, only the console. In production, the console would
  authenticate people through OIDC and the core would read the reviewer from the token; the
  authorization rules would stay as they are, since they are expressed in roles.
- Keys must be rotated by redeploying with new configuration; there is no revocation list.
