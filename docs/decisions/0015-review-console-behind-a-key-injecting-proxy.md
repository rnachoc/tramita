# ADR 0015: The review console runs behind a proxy that holds the API key

- Status: accepted
- Date: 2026-11-16

## Context

Claims handlers approve, correct or reject what the rules sent to a person. They need the facts,
the rules' evaluation, the clauses cited, the documents as read and the audit trail on one page,
and a form whose result is final money movement. The core authenticates callers with API keys
mapped to roles (ADR 0009); the console calls it as REVIEWER. There is no identity provider in
the local stack.

## Options considered

**Where the key lives.**

1. In the Angular bundle (an environment file). Anyone who opens the console can read it and
   call the core directly as REVIEWER.
2. Typed by the handler at login. Keys end up in password managers and screenshots, and the
   browser still holds a credential that can approve payments.
3. In a proxy in front of the console that adds it to `/api` requests. The browser only talks to
   its own origin and never sees a credential.
4. A backend-for-frontend with sessions and OIDC. The production answer; out of scope locally.

**Framework.** Angular (as the brief asks) with standalone components and signals, Vitest for
unit tests, Playwright for end-to-end tests.

## Decision

- **Option 3.** An unprivileged nginx serves the build and proxies `/api/` to the core with
  `X-Api-Key` from `TRAMITA_CONSOLE_API_KEY`; `npm start` does the same in development. The
  console is a compose profile (`make console-up`).
- **Strict Content-Security-Policy**: `script-src 'self'`, no inline script, no framing, same
  origin only. Angular's critical CSS inlining is off because it loads the stylesheet with an
  inline `onload` that this policy blocks.
- **The core stays the authority.** The form mirrors the core's checks for a better message, but
  the core validates again; errors show the core's problem detail. Each review carries an
  idempotency key, so a repeated click counts once.
- **The reviewer's name** is typed once per browser session and sent with each review; it is a
  label, not an identity (ADR 0009).
- **What the handler sees**: the claim as recorded, including the policyholder's description;
  documents only as read and masked; the clauses cited, with their text, from the same file the
  rules check; why the agents asked for review; the audit trail.

## Consequences

- No credential in the browser, verified end to end: Playwright checks that no request carries
  `X-Api-Key` and that no downloaded file contains the key.
- Anyone who can reach the console can review as the console. Acceptable on a developer machine
  or a closed network; production needs option 4: OIDC login, the reviewer taken from the token
  by the core, and the proxy replaced by a backend that holds per-user sessions.
- The end-to-end test found that `crypto.randomUUID()` only exists in secure contexts, so a
  console served over plain HTTP on an internal host could not open a claim. Idempotency keys now
  come from `crypto.getRandomValues`.
- The policyholder's own description is shown to the handler as written: masking protects models,
  traces and logs, not the people whose job is to read the claim.
