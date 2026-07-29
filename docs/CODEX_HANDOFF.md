# Income Desk / Kite CSV Trader - Codex Handover

**Generated:** 29 July 2026  
**Repository:** `https://github.com/vikalpsingh/stock-options-fetcher.git`  
**Current branch:** `master`  
**Latest commit:** `dd3b995` - `Implement stock options data fetching and web interface` (29 July 2026 16:03:17 +05:30)

## Objective

Income Desk is a local/AWS-hosted Python trading dashboard for Indian equity, ETF, stock-option, NIFTY options, IPO, and income-strategy research. It combines Kite Connect data with rule-based analytics and optional OpenAI research. Its primary purpose is decision support and tightly controlled order preparation/execution for covered calls, cash-secured puts, protective NIFTY spreads, exits, and ETF/equity actions.

This is a live-trading-capable application. Treat every change touching order creation, scheduling, price calculation, or risk controls as high risk.

## Repository Layout

This repository currently contains **two unrelated applications**:

- Root Next.js/Ujjain Kumbh website files such as `app/`, `components/`, `src/`, `public/`, and `package.json`.
- The active trading application in `webapp/`.

Trading work should normally remain inside `webapp/`. The root `README.md`, `webapp/README.md`, `webapp/package.json`, `.env.example`, and `webapp/deploy/nginx.conf.example` contain stale Ujjain Kumbh material and must not be assumed to document the trading application.

## Current Architecture

### Runtime

- `webapp/app.py`: large single-process HTTP application built on `ThreadingHTTPServer` / `BaseHTTPRequestHandler`; it owns HTML rendering, state, POST routes, Kite/OpenAI calls, caching, schedulers, and many business rules.
- Default bind: `127.0.0.1:8765`; controlled through `KITE_WEB_HOST` and `KITE_WEB_PORT`.
- The server starts a daemon `position_close_scheduler_loop` in process. Scheduled state is persisted through application settings, but scheduling is not an external durable job runner.
- `webapp/app_settings.json`: operational configuration, profile settings, scheduler switches, and user-controlled values. This is runtime state, not source code.

### Domain Modules

- `webapp/risk_config.py`: central option-risk thresholds.
- `webapp/risk_engine.py`: `RiskVetoEngine`, approved/rejected order generation, no-trade outputs.
- `webapp/position_lifecycle.py`: lifecycle tracking and position-risk statuses persisted in `open_positions.csv`.
- `webapp/nifty_options_engine/`: NIFTY regime, confidence, option-chain, tactical spread, order, execution, scheduler, and dashboard modules.
- `webapp/nifty_no_trade.py`, `webapp/nifty_tactical.py`, `webapp/nifty_grow.py`: NIFTY strategy/risk helpers and alternative flows.
- `webapp/income/covered_call.py`: covered-call domain logic.
- `webapp/ipo_data_service.py`, `webapp/ipo_cache.py`, `webapp/ipo_scoring_engine.py`, `webapp/ipo_screener_engine.py`, `webapp/ipo_screener_config.py`, `webapp/ipo/`: IPO data, verification, scoring, research, and symbol resolution.

### Persistence and Outputs

- SQLite: `webapp/vikalp_income.db`, including booked-P&L, income-growth holdings, and IPO research data.
- CSV/JSON runtime state: `open_positions.csv`, `trade_journal.csv`, `app_settings.json`, dated trading CSVs, `risk_outputs/`.
- Prompt source: `webapp/openai_csv_prompt.md`.

## Implemented Functional Areas

- Profile-aware Kite Setup: `Vikalp`, `Monika`, `Shanti` (default), and `Aanya`; profile-specific API key/secret/access token handling, login link, token generation, saved settings, selected-profile header badge.
- Home market cockpit, global cues, MMI, configurable Kite watchlist, and controlled quote caching/refresh.
- Research CSV parsing, option analytics, decision labels, score/risk columns, and current-position-aware GPT research.
- Trading CSV preview, lot-based input normalization, LTP/markup pricing, duplicate position/order blocking, pre-trade validation, order execution confirmation, and CE top-three cards.
- Positions, active-option analytics, premium capture, lifecycle risk monitor, exit CSV/control-loss support, and scheduled close-order guard.
- Modify/Cancel order management with open/completed separation, quote/price adjustment controls, suggestions, score, P&L context, and bulk selection.
- Income / covered-call / cash-secured-put flows, PE candidate cards, execution confirmations, and current-position/P&L summaries.
- Income Growth, holding-driven covered-call capacity, dividend income, equity LIMIT order popups, GPT validation/cache, and persistent editable holdings.
- Equity, Investing, Commodity ETF, Analytics, GPT CSV Generator, and IPO research pages.
- NIFTY Income and NIFTYGrow: regime selection, no-trade gates, confidence scoring, liquidity/credit/expected-move checks, dynamic hedge width, protective hedge reuse, tactical spread candidates, execution popups, and scheduled monitoring.
- IPO Screener with multiple public-source adapters, verification/exclusion gates, sorting, upcoming IPOs, GPT research output, and cached results.

## Important Business and Financial Rules

Read `risk_config.py` before changing risk behavior. It is the authoritative central threshold file.

- All Kite orders ultimately use **quantity**, not lots. User-facing `lots` input must be converted using the actual current instrument lot size.
- NFO limit prices must be rounded to `0.05`; zero-price limits are invalid. Quote/depth/LPP validation should occur immediately before order submission.
- New option SELL prices generally default to **20% above fresh LTP**, configurable in Kite Setup. Do not silently use a stale placeholder such as `18.5` or `0`.
- For a short CE/PE close, the passive close BUY basis is 20% below the lower of entry average and LTP. For a long CE/PE close, the passive close SELL basis is 20% above the higher of entry average and LTP.
- Intraday hard-stop/risk overrides are DTE-gated. The current default hard-stop start threshold is 9 **trading** DTE; the value is configurable in Kite Setup. Basic passive close-order protection is a separate rule and should not be accidentally removed by the hard-stop DTE gate.
- Covered CE requires actual share coverage. CSP requires assignment cash; naked CE is not permitted in normal income flows.
- Every option SELL needs target/warning/hard-stop values. The risk engine may return `APPROVED`, `REDUCE_SIZE`, `WATCH_ONLY`, or `BLOCKED`; no-trade is a valid result.
- Existing `EXIT_NOW`/warning positions, same-symbol open positions, monthly loss limits, VIX, event dates, premium yield, technical weakness, and expiry risk can block new SELL trades.
- NIFTY protective legs, existing hedge reuse, strategy selection, no-trade gates, liquidity filters, and dynamic hedge width are separate from stock-option rules. Do not weaken these checks accidentally when adding a manual override.
- Schedulers can place/modify live orders. Manual and scheduler flows must call the same pricing and validation helpers.

## External Integrations

- **Zerodha Kite Connect:** profiles, positions, holdings, order book, instruments, quotes, margins, and live orders.
- **OpenAI API:** GPT CSV generation, Income Growth validation, IPO research notes. The app uses the OpenAI Responses API.
- **Public market/news sources:** Yahoo/global quote data, MMI/news/market pages, NSE/BSE and IPO sources including NSE, IPOWatch, Chittorgarh (optional), and other source adapters.
- **Public CSV/Google Sheets:** research CSV sources may be a local file or public sheet URL.

All external sources can be unavailable, rate-limited, stale, structurally changed, or inconsistent. A failed external read must display a safe status and must never become an implicit live-order approval.

## Scheduled Jobs in `app.py`

The in-process scheduler includes controls in Kite Setup and currently covers:

- Default close orders: weekdays at 09:20 IST.
- Intraday Missing Close-Order Guard: every 15 minutes, weekdays 09:30-15:15 IST.
- Income Growth GPT CSV: weekdays at 09:30 IST.
- NIFTY entry / T-7 exit / weekly pair-exit monitoring flows, each governed by NIFTY setup switches and schedules.

Treat exact schedule values as configuration: validate in Kite Setup and `app_settings.json` before relying on them. The current source contains NIFTY defaults that have changed repeatedly; do not infer a production policy from old screenshots.

## Deployment Process

Operational deployment has been AWS Lightsail Ubuntu, reverse-proxied to the public domain, with systemd service `vikalp-income.service`. The systemd unit is not versioned in this repository.

Typical server workflow:

```bash
cd /var/www/tradingapp
git status
git pull --ff-only origin master
cd webapp
source ../venv/bin/activate
python -m pytest tests -q
sudo systemctl restart vikalp-income
sudo systemctl status vikalp-income --no-pager
journalctl -u vikalp-income -f
```

For a local Windows run:

```powershell
cd C:\Coding\NSE\stock-options-fetcher\webapp
$env:KITE_WEB_HOST="127.0.0.1"
$env:KITE_WEB_PORT="8765"
python app.py
```

For an externally proxied host, bind only according to the server firewall/reverse-proxy plan. Do not expose port 8765 publicly without authentication, TLS, and restrictive AWS networking.

## Environment and Sensitive Configuration

Never put secret values in source code, documentation, CSVs, tests, screenshots, logs, or commits. Rotate any keys previously exposed in chat/history.

Environment variable names observed in source:

- `KITE_WEB_HOST`
- `KITE_WEB_PORT`
- `KITE_DEFAULT_CSV_PATH`
- `KITE_CONFIRM_LIVE_ORDER`
- `OPENAI_API_KEY`
- `VIKALP_AUTH_SECRET`

Kite profile credentials are also managed through profile/application settings and use the conventional names `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_ACCESS_TOKEN`. Treat `app_settings.json` and `.env` as sensitive runtime files.

## Current Test Status

Validated on 29 July 2026 from `webapp/`:

```text
263 passed, 9 subtests passed, 2 failed
```

Current failures:

1. `tests/test_nifty_individual_sell.py::NiftyIndividualSellTest::test_acknowledged_single_ce_reaches_live_execution` expects the older seven-argument `nifty_income_manual_pair_snapshot` call, while code passes three additional optional arguments.
2. `tests/test_option_probability_risk.py::test_build_option_probability_risk_marks_missing_inputs_as_warning` receives `FORCE_EXIT` for missing inputs where the test expects `SAFE`, `WATCH`, or `REVIEW`.

These are documentation-only handover notes; they were not changed in this task.

## Known Defects and Technical Debt

1. `app.py` is approximately 32k lines and mixes HTML, HTTP routes, scheduler state, integrations, and business/risk logic. Focused extraction is needed before large feature changes.
2. Root and `webapp` documentation/deployment artifacts are stale and reference the unrelated Ujjain Kumbh Next.js app.
3. In-process daemon scheduling has no external queue, leader election, persistent execution lock, or job-run audit robust enough for multi-instance deployment.
4. Live quote freshness, LPP bounds, bid/ask availability, and stale CMP history are recurring safety risks. All execution windows must reuse the fresh snapshot that was used to rank a candidate, then perform only a minimal final quote validation.
5. Current CSV compatibility is broad and fragile: legacy `quantity` CSVs and newer `lots` CSVs both need to remain supported.
6. IPO public scraping is brittle. Source adapters, symbol resolution, and exchange verification often yield incomplete data; unverified/sample rows must never enter buy-zone/ranking output.
7. Runtime databases, settings, journal files, and user CSVs are colocated with application source. They need backup/retention/permissions and eventual separation.
8. The current test suite has the two failures listed above and lacks a fully mocked end-to-end scheduler/order-placement regression suite.

## Pending Work (Priority Order)

### P0 - Safety and correctness

1. Fix the two failing tests or intentionally update their assertions after validating the intended NIFTY invocation and missing-data risk behavior.
2. Add regression tests for all close-order guard outcomes: short/long, stock/NIFTY, basic passive order, hard-stop DTE gate, duplicate open close order, completed close order, and LPP retry.
3. Verify live-order safety centrally: fresh quote age, tick rounding, LPP range, bid/ask quality, profile/token validity, duplicate detection, and a clear dry-run path.
4. Move/rotate credentials from source/runtime files where necessary and restrict production filesystem permissions.

### P1 - Stability and operations

1. Version a correct trading-specific `requirements.txt`, service unit template, nginx config, `.env.example`, and deployment README inside `webapp/`.
2. Replace or wrap in-process scheduled order execution with durable job state, per-job mutexes, idempotency keys, structured audit log, and alerts.
3. Add error observability and a daily scheduler-run report before enabling unattended live execution.
4. Preserve request single-flight/cache behavior, and profile every tab before adding more background calls.

### P2 - Current feature backlog

1. IPO: Select All/Deselect All for Top 40 selection and reliable GPT shortlist persistence/output review.
2. IPO: continue improving verified source fallback and mapping; keep upcoming IPO data visible even when symbol resolution fails.
3. NIFTY: finish reconciling the revamped regime/tactical engine, confidence score, execution popup, scheduler behavior, and audit/export paths as one coherent user flow.
4. Position Risk Monitor: complete selectability/control-loss/exit CSV UX and verify its data matches current Kite positions.
5. Improve execution window speed by passing the already-fresh candidate snapshot through the modal; avoid duplicate API fan-out.

### P3 - Maintainability

1. Gradually split `app.py` by panel/route/service without changing live-order behavior.
2. Separate operational state from source tree and add migrations/backups for SQLite.
3. Replace stale Kumbh docs and isolate the two applications into separate repositories or clearly separated roots.

## Decisions Made and Rejected Approaches

- Use Kite API, not Custom GPT URLs, for app automation. Custom GPT links may be opened manually but are not a backend API.
- Use LIMIT orders; do not use unprotected market orders through Kite.
- Keep normal order CSV output Kite-compatible. Scores, reasons, risk plans, and audit fields must stay outside the Kite payload.
- Support both legacy quantity CSVs and lot-based user CSVs; normalize to actual Kite quantity after instrument lookup.
- Favour “NO TRADE” and empty approved CSVs over forcing an entry.
- Do not allow naked CE in normal income strategy. CSP must be cash backed.
- Use local cache/single-flight to reduce duplicate Kite/Yahoo calls, but never let cache replace final execution-time validation.
- IPO demo/mock data is allowed only in explicit demo mode and must be excluded from production scoring/ranking/buy zones.

## Commands

```powershell
# From repository root
git -c safe.directory=C:/Coding/NSE/stock-options-fetcher status
git -c safe.directory=C:/Coding/NSE/stock-options-fetcher branch --show-current
git -c safe.directory=C:/Coding/NSE/stock-options-fetcher log -1 --oneline

# Python tests and local app
cd C:\Coding\NSE\stock-options-fetcher\webapp
python -m pytest tests -v
python app.py

# Focused examples
python -m pytest tests\test_risk_controls.py -v
python -m pytest tests\test_nifty_options_engine.py -v
python -m pytest tests\test_ipo_feature.py -v
```

Before committing, inspect `git status`, avoid adding `.env`, runtime DBs, CSVs, logs, or credentials, and rerun the relevant tests.
