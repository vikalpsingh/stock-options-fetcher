# Engineering Instructions

## Scope and Stack

- The active trading app is `webapp/`, implemented in Python 3 with `ThreadingHTTPServer` in `webapp/app.py`.
- Core services live in `webapp/risk_engine.py`, `webapp/risk_config.py`, `webapp/position_lifecycle.py`, `webapp/nifty_options_engine/`, and IPO modules under `webapp/` and `webapp/ipo/`.
- The repository root also contains an unrelated Next.js/Ujjain Kumbh site. Do not change `app/`, `components/`, `src/`, `public/`, or root web assets for a trading-app task unless the user explicitly scopes that work.

## Architecture Conventions

- Prefer adding domain logic to an existing focused module; do not add more business logic to `app.py` unless it is route/render wiring.
- Preserve Kite-compatible CSV payload columns. Keep risk scores, audit fields, and explanations out of the final Kite payload.
- Preserve both legacy `quantity` CSV input and user-facing `lots` input. Convert lots using verified current instrument lot size before Kite submission.
- Reuse a candidate's fresh quote snapshot in execution UI, then do only the minimal final safety validation required before placing a live order.
- Treat all external sources as optional/untrusted. Missing Kite/OpenAI/IPO/news data must produce a safe state, never a crash or silent approval.
- Use cache/single-flight wrappers for expensive public/Kite reads; do not introduce page-load API fan-out.

## Financial and Order Rules

- Kite receives `quantity`, not lots. NFO prices must be valid `0.05` ticks.
- Never submit a zero/missing NFO LIMIT price. Validate quote freshness, bid/ask, LPP range, and duplicate state immediately before a live order.
- Option SELL markup and close-order rules must use settings/risk config, not hard-coded values. Current default SELL markup is configurable and normally 20% above fresh LTP.
- Covered calls require actual share coverage; CSP requires assignment cash. Do not permit naked CE in normal income flows.
- Keep hard-stop/risk exit DTE gates distinct from passive close-order protection. Both stock and NIFTY option positions need equivalent safeguards.
- Risk engine `BLOCKED`/`WATCH_ONLY`/`NO_TRADE` is a valid outcome. Never force an order merely because the UI requested candidates.
- Scheduler/manual paths must call the same order validation/pricing helpers and must be idempotent against existing orders.

## Sensitive and Runtime Files

Do not modify or commit any of these without explicit user approval:

- `.env`, credential files, API tokens, passwords, or profile secrets.
- `webapp/app_settings.json`, `webapp/vikalp_income.db`, `webapp/open_positions.csv`, `webapp/trade_journal.csv`, dated user CSV files, `webapp/risk_outputs/`, or production logs.
- `.git/` and any infrastructure state outside the repository.

Never print, echo, copy, or document secret values. Use environment-variable names only.

## Testing

- Run focused tests for each changed area, then `cd webapp; python -m pytest tests -q` for any risk/order/scheduler change.
- Tests must not call live Kite, OpenAI, Yahoo, IPO sites, or a browser. Use mocks and fixed timestamps.
- Add a regression test whenever a live-order, close-order, DTE, tick/LPP, duplicate, or risk veto bug is fixed.
- Do not claim tests pass when they do not. State exact failures and whether they predate the change.

## Definition of Done

- Scoped diff only; no unrelated UI/repository cleanup.
- Financial behavior is explained in plain language and covered by tests.
- Live-order changes preserve dry-run and explicit confirmation behavior.
- Error handling is safe, concise, and keeps the user on the relevant tab unless it is genuinely setup/auth/profile failure.
- No secret or runtime data is committed.
- Relevant tests run, Git status is inspected, and documentation/configuration is updated when behavior changes.
