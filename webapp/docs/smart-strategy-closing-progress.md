# Smart Strategy Closing Scheduler 2.0 — implementation checkpoint

Updated 2026-11-08. **NOT COMPLETE / NOT LIVE-READY.** No automatic broker submission path has been enabled. No production settings or databases were changed during development.

## Existing architecture inspected
- Application uses `KiteWebHandler`/BaseHTTPRequestHandler, not Flask; retain its existing routes.
- `app.py:scheduled_job_definitions`, `position_close_scheduler_loop`, `plan_position_close_job`, `run_position_close_workflow`, `execute_position_buy_orders`: existing daily/interval workers share close planning and durable close-intent handling. Existing protected executions already exclude owned contracts from generic close orders.
- `trade_protected_execution.py`: durable baskets, order/trade reconciliation, CAS submission; current hedge-close path requires all shorts closed, so it must not be reused unchanged to claim per-pair partial release support.
- `nifty_options_engine/ledger.py`: existing strategy IDs already group all four iron-condor legs, with separate fills/orders and account/mode isolation.
- `nifty_options_engine/service.py`, `page.py`, `analytics.py`: entry registration, exit checks, monthly actual-fill reporting; reuse rather than create a competing P&L ledger.
- `execution_pair_analytics.py`, `trade_pair_exit.py`, `kite_pair_scheduler.py`, `dhan_it_pair_execution.py`: relevant pair/monitor integration points. DHAN data must remain broker-isolated; it is not yet wired to this feature.

## Completed milestone
1. `smart_closer_config.py`: validated default disabled/dry-run policy, 10% initial-capital target, 09:00 reconciliation / 09:25–15:20 five-minute scan configuration, mandatory safety settings.
2. `smart_closer_repository.py`: additive metadata over existing strategy/fill ledger. Stable group ID equals existing strategy ID; deterministic CE/PE pair IDs; no inferred condors, no duplicate fills. Audited account configuration, explicitly verified frozen capital with versioned adjustments, locked target overrides. Account/mode filtered access.
3. New NIFTY entry reviews register group membership before submission. Ticket metadata now carries instrument-master name/exchange/tick size. Entry signals, strikes, MMI and directional veto calculations are untouched by this task.
4. `smart_closer_engine.py`: combined-group executable liquidation valuation, fees/slippage, target feasibility, quantity-safe reconciliation, scheduling predicate and confirmed-fill hedge-release arithmetic.
5. `smart_closer_service.py`: callable read-only Kite positions/orders/trades/NFO reconciliation; imports only fills for previously registered order IDs; failures invalidate daily approval. Dry-run valuation has no broker mutation capability.

## Database additions
Additive `smart_closer_config`, `smart_strategy_groups`, `smart_strategy_pairs`, `smart_closer_audit`, and reserved `smart_exit_intents` tables. Existing `nifty_strategies`, legs, order events and fills remain authoritative. No second P&L/fill store. Schema creation occurs on explicit repository initialization/entry registration, not module import.
Capital is never inferred from preview margin, account balance or option notional. A verified source and audit evidence are required; initial capital remains unverified until every entry quantity has actual fills.

## Implemented formulas
- target INR = frozen initial capital × effective target % / 100.
- liquidating open short = actual entry average minus executable BUY depth price, times remaining quantity.
- liquidating open long = executable SELL depth price minus actual entry average, times remaining quantity.
- estimated net group profit = realised gross + complete open liquidation gross − actual ledger charges − estimated remaining charges − slippage allowance.
- ROI = estimated net group profit / frozen capital × 100.
- Released hedge quantity = remaining hedge − pending hedge sells − outstanding matched short; invalid protection blocks.
No live trigger may use these calculations until the coordinator and authorization gates below are completed.

## Validation
63 passed:
`python -m pytest tests/test_smart_closer.py tests/test_nifty_ticket_service.py tests/test_nifty_page.py tests/test_nifty_directional_trend.py -q -p no:cacheprovider --basetemp=.codex-test-tmp/smart-closer3 --tb=short`
Fixtures cover standalone CE/PE and four-leg registration, restart/idempotency, cross-expiry rejection, shared-symbol allocation, account/mode separation, frozen capital/target overrides, net-vs-gross target, target unreachable, partial realised fills counted once, stale data, broker failure invalidation, pending orders, missing hedges, symmetric winning-wing/losing-wing regressions, release arithmetic and scan times. Existing NIFTY lifecycle and DTV tests pass. No app.py import, network, live orders or runtime database mutation.

## Remaining implementation — resume here
1. Durable group exit coordinator: persist/claim one intent, integrate existing execution CAS and common scheduler/manual ownership locks; submit price-protected tick-rounded/freeze-sliced BUY closes; confirm actual fills; immediately release only corresponding hedge quantities. Handle timeout/restart/rejection safely. No speculative fills or blind retries.
2. Persist scheduler run ownership and daily reconciliation success; connect existing worker to 09:00 reconciliation and five-minute scans; separate immediate execution worker from scan cadence.
3. Exclude managed quantities from all legacy routine individual-leg workers at final submission too; preserve emergency controls and explicit manual-order ownership review (no automatic cancellations).
4. Authorized administration UI and existing-app routes: save settings/targets, audited capital overrides, manual legacy pair/group registration, unmatched/error/history views, asynchronous state display. Do not expose an active LIVE control before complete verification.
5. Registration adapters for TRADE and applicable DHAN-IT records; never infer cross-broker/account ownership or group by expiry alone.
6. Sync actual group closing fills to existing monthly ledger, preserving month attribution and exactly-once fees/accounting. No duplicate settlement ledger.
7. Complete requested coordinator/race/timeout/restart/freeze-limit tests. Read-only real-position dry-run and several market-session observations remain deployment validation, not performed here.

## Deployment/rollback
Do not activate or describe this checkpoint as the completed replacement scheduler. Defaults remain disabled/dry-run and existing workers remain unchanged. Use the established serialized deployment with previous SHA retained, back up SQLite consistently before any production migration, and restart normally. Roll back application code to prior SHA if necessary; preserve additive tables and all fills/runtime data. Do not delete tables, logs, configuration or runtime files during rollback. Before eventual LIVE activation, verify account API permissions, outbound IP and applicable broker requirements, then require explicit admin activation after dry-run acceptance.


## Milestone 2 — 2026-11-09: durable intent and partial-fill exit planning
Completed `smart_closer_exit.py` and `tests/test_smart_closer_exit.py`:
- SQLite-serialized, idempotent group intent creation re-evaluates complete-group profitability against the saved capital and target. Concurrent requests/restarts reuse one intent; intent freezes all pair/leg identities and mode.
- Pure fill-ledger-based action planner proposes short buybacks and only the corresponding released hedge quantities, subtracting pending hedge sales. One closed wing leaves PARTIAL_GROUP_EXIT; no fabricated fills or automatic retries.
- Rejected/cancelled orders stop proposals (FAILED_SAFE). Ambiguous submissions, missing trade allocations and incomplete order snapshots require reconciliation. All ledger quantities closed still require final broker-flat verification before CLOSED.
- Existing generic reconciliation now preserves CLOSING while an exit intent exists, instead of resetting it to ACTIVE_VERIFIED or prematurely marking it CLOSED.
- Stable 20-character order-tag generator prepared for the execution adapter.
Validation: 48 focused tests passed across `test_smart_closer_exit.py` and `test_smart_closer.py` (temporary SQLite, synthetic fills, no broker calls). No existing scheduler, runtime data or production setting changed.

**Boundary:** these are proposals and durable intents, not executable broker orders. No route/worker invokes them yet. They do not claim shared manual/scheduler submission locking or LIVE readiness. Next implement atomic action reservation in the existing execution record, fresh exit validation, tick/freeze/slippage handling, broker adapter dispatch and actual order/fill reconciliation. Then wire the immediate coordinator worker, five-minute scheduler and administration UI. Monthly ledger integration and remaining rollout work above remain outstanding.
