# Repository Code Review Rules

These rules apply to all changes in this repository.

## Broker and order execution safety

- Treat Zerodha Kite, DHAN, and any broker/order API integration as high-risk code.
- Do not place, modify, or cancel live broker orders from tests, CI, or review tooling.
- New order-placement paths must keep explicit user acknowledgement, visible max-loss/risk data, and existing guardrails unless a task explicitly changes them.
- Prefer paper/simulated execution in automated checks.
- Any live execution change must include clear logs that do not expose credentials, tokens, or personal account data.

## Risk engine guardrails

- Do not bypass `risk_engine` or related spread/liquidity/max-loss checks silently.
- If a rule is relaxed, document the exact condition, scope, and safety tradeoff in code or tests.
- Keep hard-blocking behavior for undefined-risk or unhedged trades unless the user explicitly requests a controlled repair/override flow.

## Tests

- Tests must not call live broker APIs, external order endpoints, or mutate production/runtime data.
- Mock broker adapters, market data, news/result-date lookups, and order books.
- CI should compile Python and run pytest when Python tests exist.

## Secrets and runtime data

- Never commit `.env`, broker credentials, Kite/DHAN access tokens, API keys, session cookies, order exports, logs, uploaded files, local SQLite runtime databases, or generated trading CSVs.
- Do not print secrets in application logs, deployment logs, CI logs, screenshots, or test failures.
- Runtime data belongs on the server and must be preserved across deploys.

## Deployment safety

- Do not use `git clean` in deployment scripts. Runtime files may live beside the app.
- Deployment must support rollback to the previous Git SHA if validation or service restart fails.
- Production deployments must be serialized with concurrency control.
- Do not rename `master` to `main`; `master` is the production branch.

## Review focus

- For every PR touching trading, broker, risk, scheduler, or deployment code, reviewers should check:
  - no live broker calls in tests;
  - no committed credentials or token-like files;
  - no destructive runtime-data deletion;
  - no broad filesystem cleanup;
  - rollback behavior for deployment changes;
  - clear user-facing risk messaging for order execution.
