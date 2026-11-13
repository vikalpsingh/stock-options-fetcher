# NIFTY Market & Risk fixes — checkpoint 2026-11-12

## Implemented and verified
- NIFTY-scoped offline 2026 NSE session calendar, weekday/weekend/holiday, unknown-year fail closed, explicit Muhurat schedule. No request-time web scraping.
- Sources: NSE FAOP71777 / CMTR71775 annual calendar; FAOP72262 January 15 election override; FAOP76940 November 8 Muhurat 14:20–15:40. https://www.nseindia.com/resources/exchange-communication-holidays supplies current market timings.
- NIFTY service passes session information to the existing cached indicator loader. TRADE callers retain previous behavior.
- Closed sessions do not request intraday candles or call yesterday's quote unexpectedly stale. Historical candles remain visible, timestamps retained. Missing movement displays N/A.
- Freshness validator separates FRESH, EXPECTED_PREVIOUS_SESSION, STALE_DURING_MARKET, MISSING, SESSION_CLOSED; loader failures carry API_ERROR.
- Final server ticket check blocks closed/unknown sessions, stale/missing mandatory evidence, unknown/locked monthly ledger, and selected-side DTV veto. Quick-pair advisory override cannot bypass this final check. Existing exit/repair paths unchanged.
- Dashboard shows session, previous/next date, execution reserve, monthly booked loss usage and remaining allowance separately. Monthly state presentation uses 50/75/100 thresholds and preserves hard lock.
- Normalized EMA slope: raw existing 3-session EMA difference / previous EMA * 100. Raw indicator engine unchanged; chart/card reuse same history snapshot.

## INR 500 discrepancy root cause
risk_validator.calculate_nifty_portfolio_risk adds estimated_execution_costs_inr (default 500) to projected expiry loss, including portfolio-only assessment. UI previously showed current loss alongside cap-minus-projected risk without revealing costs. Thus 60000 - 32194.50 - 500 = 27305.50. Now labeled execution cost reserve; no fabricated monthly reserve or removal of risk costs.
Monthly risk repository uses max(0, -booked_pnl), independently of theoretical open risk. Its persisted sticky hard lock remains authoritative. UI uses Decimal for remaining monthly allowance.

## Validation
65 passed:
python -m pytest tests/test_nifty_market_session.py tests/test_nifty_directional_trend.py tests/test_nifty_ticket_service.py tests/test_nifty_page.py tests/test_trade_directional.py -q -p no:cacheprovider --basetemp=.codex-test-tmp/nifty-session-final --tb=short
Mocked data/temp DB only. No app.py import, runtime database edits, broker orders, or deployment.

## Still required for full attachment acceptance
- Existing account ledger unrealised field is a position snapshot, not verified month-opening MTM change. UI explicitly labels this limitation; do not claim cross-month accounting fixed. Implement an audited month-opening mark using existing ledger, scoped carefully to avoid changing other strategies.
- Monthly display thresholds currently fixed 50/75/100; align configurable thresholds with existing account risk configuration without weakening stricter controls.
- Session calendar recognizes Muhurat and F&O close 15:40, but existing indicator continuity engine assumes 09:15 start/15:30 end. Nonstandard intraday confirmation fails closed; adapt NIFTY-only candle windows and test actual special-session dataset before enabling such entries.
- Verify official future calendar versions/additional unscheduled overrides before new year. Unknown years block; no automated calendar update added.
- Complete independent CE/PE final readiness UI and meaningful caution/opening-range states; existing selected-side ticket check is enforced.
- Add structured diagnostics and fuller API/missing-data error display; do not log broker exception strings or credentials.
- Browser visual verification and representative read-only real-market snapshots not performed.

## Deployment / rollback
No schema migrations. Review changes with other uncommitted work preserved; deploy only after remaining acceptance work. Retain previous application SHA and restart through existing serialized deployment process. Roll back code to prior deployment SHA; never reset settings/database files or use git clean. Calendar is local versioned code and requires verified annual maintenance.
