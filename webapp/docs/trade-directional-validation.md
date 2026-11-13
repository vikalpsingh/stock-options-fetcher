# TRADE directional validation

Implemented 2026-11-10. Scoped to TRADE; earlier uncommitted NIFTY/scheduler work and runtime files preserved.

## Files and reuse
- `trade_directional.py`: stock/sector/market context, final decision, structured TRADE_DTV logs and compact UI adapter.
- `app.py`: TRADE scan, selected-stock load, review authorization, compact DTV table cell and expandable selected-option panel. Existing technical scoring is unchanged; DTV only gates final eligibility.
- `tests/test_trade_directional.py`: mocked history, risk decisions, chart dataset consistency and isolated server authorization tests.
- Reuses NIFTY `directional_trend` calculations, `directional_market.historical` throttling/retry transport and NIFTY-specific market loader, plus `directional_ui` charts. Those modules were not changed for this request.

## Data and decisions
Actual NSE master token is resolved for each stock. Sector lookup uses existing `SECTOR_INCOME_UNIVERSE` and `SECTOR_INDEX_CONFIG`; ambiguous/missing mappings show SECTOR UNAVAILABLE. NIFTY options use existing NIFTY context directly. Stock history never substitutes NIFTY history.
Read-only Kite historical day/5minute and quote calls use the existing client and cache. Daily history is cached; short-lived snapshots refresh at review/authorization. Completed candles, daily freshness, current-session continuity and real stock volume are required. Volume-free sector indices never fabricate VWAP. Missing intraday evidence blocks entry but retains confirmed daily chart history.
Strong bull/early bull blocks CE SELL; strong bear/early bear blocks PE SELL. Sector/market conflict or unavailable confirmation adds caution without overriding the stock veto. RSI/MMI cannot override it. Shared thresholds remain ADX25, developing ADX20–25, ER .70/.35, five-day move 2%, gap .75%. EMA slope is displayed as the three-session EMA change / EMA20 ×100.
Buy orders, verified same-contract/product/exchange position reductions and non-option sales are exempt from this added veto; existing checks still apply. Covered calls default to blocking directional risk; an explicitly configured `TRADE_DTV_COVERED_CALL_POLICY=WARNING` allows warning-only treatment when fresh server holdings cover quantity and no competing contract order exists. No new UI override or automatic config mutation was added.

## UI and enforcement
One compact DTV column exposes stock/sector trend, ADX, ER5, final decision and candle timestamp without adding six wide columns. The selected-option panel expands into summary plus ER, ADX/DMI and price/EMA charts, with 1/3/6-month history and isolated element IDs. Charts and summary read the same dataset. Stale saved scan eligibility is invalidated on rendering.
Server review checks run before initial submission and renewed short authorization. Direct requests cannot use a browser-supplied DTV result. Existing exits, EXECUTION monitor, pair registration, DHAN-IT, closing schedulers, other route handlers and NIFTY calculations were not changed by this task.

## Validation and limits
53 focused tests passed across test_trade_directional, test_trade_selection_binding, test_trade_manual_hedge, test_trade_ce_hedge, test_trade_blocked_spread_display, test_trade_opportunity_engine and test_trade_direction_engine. Includes an executed isolated renewed-short authorization rejection, source-boundary check for initial submission, mocked history/API failures, shared-cache reuse, valid stock VWAP, missing sector data and chart JSON/JavaScript syntax. Python source compilation passed without importing app.py. No live orders, broker network calls, production settings or runtime databases modified.
Browser appearance and actual account historical-data entitlement remain deployment checks. After normal deploy/restart, recalculate the TRADE scan and select a stock; expand Trend Strength & Directional Risk, inspect source timestamps and test PAPER review. Never use a LIVE order to test the integration. Existing runtime databases/settings must be preserved across deploy/rollback.
