# NIFTY 2.0 directional trend filter

Implemented 2026-11-07. Scoped to NIFTY 2.0; no runtime settings/databases changed.

## Implementation
- `nifty_options_engine/directional_trend.py`: completed IST candles, causal indicators, daily and opening-gap directional veto, fail-closed evidence validation.
- `directional_market.py`: authenticated Kite spot token discovery, historical reads, nearest liquid futures VWAP, account/session-scoped existing cache, serialized history requests and bounded HTTP 429 backoff, `NIFTY2_DTV` diagnostics.
- `directional_ui.py`: panel beside existing MMI (stacked on mobile), reasons, timestamps, MMI conflict/final decision, lightweight-charts 5.0.9 ER/ADX-DMI/close-EMA views, 1/3/6-month selection, hover and historical veto markers.
- `config.py`, `service.py`, `ticket.py`, `ui.py`, NIFTY 2.0 context loader in `app.py`: integration into existing preview, optimizer, review and fresh server entry approval. Existing exit approval remains separate.
- Focused directional tests plus existing ticket/page/optimizer fixtures. Optimizer cap tests now explicitly specify their intended INR 60,000 test budget rather than depend on the application default.

## APIs and calculations
Read-only `kite.instruments('NSE')` fallback for dynamic NIFTY 50 token, existing NFO master for futures, `kite.quote`, `kite.historical_data` day/5minute. No new order API or scheduler.
ER(n) = abs(close - close[n]) / sum(abs(daily changes)), zero for flat denominator. Wilder ADX/DMI14 and ATR14; EMA20 seeded with SMA and three-session EMA slope; signed five-session return; preceding five completed closes for breakouts; consecutive higher/lower closes.
ER5 >= .70 plus signed five-session move >= 2% and preceding-five-close breakout blocks countertrend shorts. ADX >=25 uses DI direction; rising ADX20–25 adds caution. Caution requires fresh prices, full executable depth, configured spread limit and bounded payoff. Gap >=.75% veto uses completed spot candles/opening range and corresponding futures own volume-weighted typical-price VWAP for continuation; no index-volume VWAP. Missing evidence blocks fresh entries. Nested `directional_trend_veto` configuration supplies thresholds.
MMI remains unchanged and cannot override a directional BLOCK. Selection and prices are preserved for inspection; entry eligibility changes. Existing exits remain available under their own checks.

## Validation
40 passed:
`python -m pytest tests/test_nifty_directional_trend.py tests/test_nifty_ticket_service.py tests/test_nifty_page.py tests/test_nifty_optimizer.py -q -p no:cacheprovider --basetemp=.codex-test-tmp/dtv-routes --tb=short`
Python compilation of changed modules/app source (without importing app.py), JavaScript syntax via node, and git diff whitespace check passed. All broker/data responses mocked; temporary databases only; no LIVE calls.

## Limitations and deployment verification
- Requires authenticated Kite historical entitlement. Expired credentials, missing history, stale quotes or required futures evidence block fresh entry; fix data access rather than bypassing the checks.
- Daily values use completed sessions, not current unfinished daily candles. Intraday confirmation uses completed five-minute candles, so initial session warm-up can block both directions.
- Fetches 600 calendar days for daily warm-up/chart history; charts show available history only. Existing in-process cache is reused; request throttling is local to this feature/process.
- Chart library uses the existing CDN dependency. Its failure does not disable server validation.
- Browser appearance and real broker data access have not been verified locally.
- Deploy normally with rollback available, restart app, verify historical entitlement and IST timestamps in PAPER, inspect 1/3/6-month charts at desktop/mobile sizes, verify MMI conflict messaging and refresh eligibility, then inspect `NIFTY2_DTV` diagnostics. No test LIVE orders required.
