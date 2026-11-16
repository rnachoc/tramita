# Review console

The claims handlers' console: an inbox of claims waiting for a person, each claim with the
rules' evaluation, the cited clauses, the documents as read, the fraud signals, why the agents
asked for review and the audit trail, and a form to approve, correct or reject.

Angular 22 (standalone components, signals), Vitest for unit tests, Playwright end to end. The
interface is in Spanish, as the insurer's internal tool.

```bash
make console-install   # npm ci
make console-test      # formatting and unit tests
make console-up        # build and serve on :4200 behind nginx (core running on the host)
make console-e2e       # approve a claim through the console in a real browser
```

The browser never holds an API key: nginx serves the build and proxies `/api` to the core,
adding the REVIEWER key from `TRAMITA_CONSOLE_API_KEY`
([ADR 0015](../../docs/decisions/0015-review-console-behind-a-key-injecting-proxy.md)).
For development, `npm start` does the same with `proxy.conf.mjs`. The policy clauses are copied
from `data/policies/clauses.json` before every build.
