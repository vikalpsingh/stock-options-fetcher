# Income Desk - Work Tracker

**Branch:** `master`  
**Baseline commit:** `dd3b995` (`Implement stock options data fetching and web interface`)  
**Updated:** 29 July 2026

## Completed

- Profile-aware Kite Setup with Shanti as the default profile and support for Vikalp, Monika, and Aanya.
- Live trading dashboard, research CSV workflow, option analytics, order preview/execution, Modify/Cancel, positions, income, income growth, equity, investing, commodity ETF, GPT, IPO, NIFTY Income, and NIFTYGrow sections.
- Central `risk_config.py`, `risk_engine.py`, `position_lifecycle.py`, risk outputs, and trade journal foundations.
- Lots-based CSV input normalization with actual Kite quantity calculation.
- 20% configurable SELL markup, limit-price tick/LPP safety helpers, duplicate checks, and scheduled close-order guard.
- NIFTY regime/no-trade/confidence/liquidity/credit/hedge strategies and scheduler controls.
- IPO source adapters, verification gates, cached data, GPT research support, and no-demo-in-production direction.
- Test suite: 263 passing tests and 9 passing subtests as of this handover.

## In Progress

### Test-suite regression cleanup

- `test_nifty_individual_sell.py` has a mock signature mismatch after optional snapshot parameters were added.
- `test_option_probability_risk.py` expects missing-data warning behavior but current code yields `FORCE_EXIT`.

**Acceptance criteria**

- `python -m pytest tests -q` completes with zero failures.
- Tests confirm the intended risk behavior, not merely the old function signature.
- No test uses live Kite, OpenAI, or public market data.

### IPO data and research usability

- Keep next-seven-day IPOs visible even if security mapping cannot resolve a tradable symbol.
- Complete Top 40 Select All/Deselect All, GPT shortlisting, popup response, and persistent research retrieval.
- Harden source fallback and clean company-name/symbol/Screener resolution.

**Acceptance criteria**

- Top 40 can be sorted and selected in bulk.
- Unverified/mock companies are excluded from rankings and buy-zone recommendations.
- Upcoming IPOs display dates, GMP, GMP %, type, sector, and source without requiring an exchange symbol.
- GPT output can be saved and re-opened without exposing API keys.

## Next - P0 Safety

### Close-order guard verification

Confirm a single authoritative path for scheduled/manual close pricing and DTE gating.

**Acceptance criteria**

- Short CE/PE: passive BUY order uses 20% below lower of LTP/average entry.
- Long CE/PE: passive SELL uses 20% above higher of LTP/average entry.
- Hard-stop override applies only at or inside configured trading DTE threshold.
- NIFTY and stock NFO positions both appear in Position Risk Monitor and scheduler logic.
- Existing matching open/complete close orders are skipped idempotently.
- All scenarios have mocked unit tests and dry-run audit rows.

### Execution safety contract

Consolidate quote freshness, LPP, bid/ask, tick, profile, and duplicate safeguards before every live order.

**Acceptance criteria**

- No NFO limit order is submitted with zero/missing price.
- All live execution modals show quote timestamp, LTP, chosen limit, reason, and any fallback adjustment.
- Quote/depth failures disable submission safely.
- One LPP rejection retry is permitted with logged old/new prices; no repeat loop.

### Credentials and deployment hardening

Remove sensitive operational state from version control and create versioned trading deployment artifacts.

**Acceptance criteria**

- No secrets in Git history/new files, docs, tests, or browser-visible defaults.
- Trading-specific `requirements.txt`, `.env.example`, systemd template, nginx template, and deployment instructions are versioned in `webapp/`.
- `vikalp-income.service` has `Restart=always` and safe restart behavior.

## Next - P1 Reliability

### Scheduler durability and observability

**Acceptance criteria**

- Per-job lock/idempotency prevents duplicate order placement.
- Job state records started/finished/outcome/profile/order IDs.
- Pause/Start/Run Now controls are safe and audited.
- Failed jobs surface a non-secret diagnostic and alert path.

### Performance

**Acceptance criteria**

- Home is lightweight by default; expensive global data uses explicit refresh or bounded TTL.
- Execution popup reuses the parent candidate snapshot and only makes minimal final validation calls.
- Kite quote/order/instrument calls share cache/single-flight protection.
- Performance is measured with timing logs before/after changes.

## Next - P2 Product Work

### Position Risk Monitor UX

**Acceptance criteria**

- Current Kite option positions populate selectable lifecycle rows.
- `CONTROL LOSS` only exposes eligible rows and explains price/action.
- Exit CSV separates BUY exits from new SELL entries.
- Status colors and action reasons are consistent with `PositionLifecycleManager`.

### NIFTY strategy consolidation

**Acceptance criteria**

- One consistent regime/tactical workflow powers dashboard, review popup, manual orders, and schedules.
- Existing long hedge reuse is correct by expiry, side, quantity, and user setting.
- Confidence/no-trade decision blocks entry only, never risk-reduction exits.
- NIFTY lot size comes from current instrument data and remains configurable only where justified.

### `app.py` decomposition

**Acceptance criteria**

- Route/panel/service extraction occurs in small, tested slices.
- No live-order behavior changes as part of a refactor-only pull request.
- Imports are acyclic and application startup stays deterministic.

