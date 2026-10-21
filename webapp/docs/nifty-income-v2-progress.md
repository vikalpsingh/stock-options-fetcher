# NIFTY Income 2.0 — implementation checkpoint

Updated 2026-10-21. Full user requirements: `docs/nifty-income-v2-request.txt`.
This is an in-progress implementation, NOT production-ready acceptance.

## Constraints

- Preserve all pre-existing uncommitted changes, especially TRADE protected execution.
- Never place, cancel or modify live broker orders in tests.
- Do not import `app.py` in tests: it initializes local runtime state.
- Test pure functions, AST-extracted app functions, mocks and temporary SQLite databases.
- Do not edit runtime `app_settings.json`, `vikalp_income.db`, credentials or exports.
- Run focused tests by phase, not the entire repository suite.
- User authorized continued work after usage resets. Hourly chat heartbeat:
  `continue-nifty-income-2-0`. Disable when all acceptance criteria pass.

## Phase 1: architecture inspected

Frontend is server-rendered HTML/CSS/vanilla JavaScript in Python `app.py`
(`BaseHTTPRequestHandler`, `ThreadingHTTPServer`); do not follow the unrelated
Next.js travel-site README.

| Area | Existing implementation / reuse |
|---|---|
| NIFTY dashboard/routes | `render_nifty_income_panel`, `/nifty-income/*` in app.py |
| NIFTY ticket | `nifty_income_manual_pair_snapshot`, `build_selected_nifty_execution_candidate`, pair review JS/countdown |
| Position actions | `nifty_position_action_candidate_snapshot`, `place_nifty_position_action_order` |
| NIFTY order placement | `execute_nifty_orders` in app.py; currently unsafe acceptance-only BUY gating |
| TRADE protected execution | `trade_protected_execution.py`, SQLite CAS/idempotency, BUY-first, explicit confirm-SELL and reconciliation |
| Kite session/data | `kite_orders.kite_client()`, cached Kite functions; ttl_seconds=0 for fresh checks |
| Existing risk | `risk_engine.py`, `monthly_risk_control.py`, `nifty_options_engine/risk_validator.py`, app risk wrappers |
| Strategies/quotes | `nifty_tactical.py`, `nifty_grow.py`, `nifty_options_engine/workflow.py` |
| SQLite | APP_DB_PATH in app.py; repository classes use additive CREATE TABLE IF NOT EXISTS |
| P&L/import | `pnl_service.py`, `kite_pnl_importer.py`, existing P&L routes |
| Exit jobs | `run_nifty_income_time_exit_job`, `run_nifty_weekly_pair_exit_monitor`, `position_close_scheduler_loop` |
| Scheduling | existing app loop, `kite_pair_scheduler.py`, `nifty_options_engine/scheduler.py` |

Dependency sequence: reconciliation/master metadata → shared portfolio payoff →
verified quote ticket → durable hedge-first executions → fill/strategy ledger →
attributed fees/imports → safe exit/hedge cleanup → monthly analytics → UI consolidation.

## Phase 2: implemented foundation

- `nifty_options_engine/reconciliation.py`: pure normalized position reconciliation,
  same account/recorded strategy/expiry/type/direction, quantity allocated only once.
  Missing ownership/metadata is blocked, not guessed from compatible symbols.
- Canonical `calculate_nifty_portfolio_risk` added to existing risk_validator.py.
  Exact piecewise-linear option expiry payoff at zero and strike breakpoints, with
  call-tail detection. Same account/expiry netting; different expiry losses added.
  Actual fill average cost for current positions; bid/ask for proposed orders.
  Conservative execution-cost argument; hard ceiling of 60000.
- Current and projected risk wrappers in app.py now use canonical service.
  Unknown exposure has None risk/budget, FAIL entry gate, explicit UNKNOWN /
  UNCAPPED labels in server HTML and ticket JavaScript.
- Portfolio read failure now blocks pair review instead of treating positions as empty.
- NIFTY position metadata now obtained from NFO master instead of inferred monthly expiry.
- Existing hedge-integrity workflow uses same reconciliation; partial hedge blocks entries.
- Position-action risk gate no longer converts unknown risk to zero or permits
  SELL_AGAINST_LONG to override the portfolio cap. BUY-only repair remains available.
- `allocate_nifty_positions` now validates recorded allocations against broker net
  positions, rejects duplicate fill/allocation IDs, wrong instrument identity,
  over-allocation, missing broker positions and pending hedge disposal. Shared-symbol
  broker MTM is apportioned by quantity. Canonical risk accepts optional allocation
  and pending-order inputs.
- `nifty_options_engine/ledger.py` adds `NiftyStrategyRepository` with idempotent
  strategy creation, immutable account/order ownership, duplicate-safe confirmed
  fill ingestion and remaining-position allocations. Unknown order fills remain
  UNMATCHED; no inferred ownership. PAPER/LIVE records are segregated.
- `nifty_option_positions` now fetches fresh positions and attaches LIVE ledger
  allocations after enriching from NFO master. Allocations use actual fill costs.
- Additive schema (not executed on runtime DB during tests):
  `nifty_strategies`, `nifty_strategy_legs`, `nifty_order_events`, `nifty_fills`.
- Legacy `calculate_nifty_defined_risk` now delegates to `strategy_risk_summary`
  in the existing canonical risk module. It uses actual leg quantity/expiry and
  executable quote prices, not the historical default lot arguments, invented
  hedge legs or LTP. `validate_nifty_strategy` also incorporates canonical risk.

### Remaining Phase 2 integration work (do first)

- Existing pre-ledger broker positions intentionally show unresolved/unhedged until
  actual allocations exist. Add user-reviewed assignment/import from verified
  order/fill IDs; do NOT guess ownership from compatible symbols.
- Ledger API and allocation reconciliation exist; connect execution order/fill
  ingestion and the reviewed assignment UI. Pass fresh pending orders from app
  callers to canonical risk (service has support, callers not all wired yet).
- Lifecycle groups PARTIAL_SPREAD, SHORT_CLOSED_HEDGE_OPEN, FULLY_CLOSED need ledger
  evidence, not guesses; current group output is conservative.
- Manual pair scalar risk (`calculate_nifty_manual_pair_risk`) and Grow helpers
  still have separate arithmetic. Finish replacing their computations with
  canonical adapters; keep broker margin separate from maximum loss.
  Cockpit packed candidate previews lack explicit hedge quote legs; they now fail
  closed until expanded from verified master/quotes.
- Estimated execution costs default to zero until fee settings are wired.
- Verify repair geometry and quantities with new AST tests before extending actions.
- Independent regime/monthly guards remain. Wire authoritative monthly ledger
  data into entry approval rather than trusting client warnings.

## Phase 3 next: urgent execution work

The unsafe legacy `execute_nifty_orders` entry path now rejects every new SELL
batch before broker access, including naked overrides. PAPER/DRY_RUN now return
previews without broker access. The final durable NIFTY path is not connected yet;
LIVE NIFTY entries intentionally remain disabled at this boundary. Existing
BUY-only repairs and exits retain their separate paths.

`income_v2_config` adds requested defaults and validates settings; hard cap <=60000,
review >=10s, master lot sizes, monthly guard and hedge requirements cannot be
disabled by ordinary settings. Merged into existing `nifty_income_config`.
Settings form and saving new v2 fields remain to implement.

Existing exit batches still use a reason string to identify exits; replace with
actual risk-reduction validation against fresh positions and pending orders.
Do not claim completed hedge-first safety for NIFTY yet. Reuse/extend the durable TRADE
execution service (currently two-leg only) for condors and NIFTY; do not create
another broker service. Persist intentions, order IDs, fills, retries/idempotency.
Block naked overrides under v2. Defaults SUGGESTION_ONLY, live_enabled=false.
SERVER must validate review nonce/countdown, monthly guard, fresh quotes,
master lot size, positions/orders and canonical aggregate risk before each SELL.
TEST/PAPER must never reach live adapters.

## Phases 4–7 pending

The four core ownership tables above exist; full P&L/import/analytics UI remains.
Reuse existing P&L repositories; add the remaining requested strategy-level tables
non-destructively. Do not infer October month net profit from the three winners.
Implement complete-spread exit/hedge cleanup and actual-fill accounting before
monthly statistics/scaling recommendations. Consolidate UI into four sections,
retaining critical risk warnings outside Advanced Details.

## Verification and local startup

Focused check command (does not import app or call brokers):

    python -m pytest tests/test_nifty_portfolio_risk_v2.py tests/test_nifty_workflow.py -q -p no:cacheprovider

Results:
- Risk foundation/workflow: 32 passed.
- Ownership/allocation repository: 12 passed using
  `python -m pytest tests/test_nifty_strategy_allocations.py -q -p no:cacheprovider --basetemp=tmp/nifty-v2-allocation-tests`.
- Initial combined test attempt had 12 fixture errors because pytest could not
  create sandbox temporary directories; the workspace-local retry passed.
- Syntax check passed for app.py, reconciliation.py, ledger.py, risk_validator.py,
  workflow.py before the latest execution-boundary/config changes.
- Execution-boundary/config tests: 12 passed in 17.60s.
- Final milestone command:
  `python -m pytest tests/test_nifty_portfolio_risk_v2.py tests/test_nifty_strategy_allocations.py tests/test_nifty_v2_execution_boundary.py tests/test_nifty_workflow.py -q -p no:cacheprovider --basetemp=tmp/nifty-v2-milestone-check`
  **58 passed in 33.13s**. Includes new canonical legacy-summary tests.
- A final small repair-risk fix preserves missing/invalid candidate loss as unknown
  instead of zero; affected AST wrapper test passed separately (1 passed in 15.94s).
- `git diff --check` passed (only repository line-ending warnings).

Syntax verification must use compile(source, ..., "exec") or AST, without importing
app or writing bytecode.

Local entry point: `python app.py`; defaults http://127.0.0.1:8765.
Do not start the full application during testing until scheduler/live flags are
isolated: startup launches the position-close scheduler. PAPER verification
currently means pure/mocked tests, not clicking legacy NIFTY live GO.

## Files changed for this milestone

Existing: `app.py`, `nifty_options_engine/config.py`,
`nifty_options_engine/risk_validator.py`, `nifty_options_engine/workflow.py`,
`tests/test_nifty_workflow.py`.

New: `nifty_options_engine/reconciliation.py`, `nifty_options_engine/ledger.py`,
`tests/test_nifty_portfolio_risk_v2.py`, `tests/test_nifty_strategy_allocations.py`,
`tests/test_nifty_v2_execution_boundary.py`, and this progress/request documentation.

Other modified/untracked TRADE files and runtime files predate this NIFTY work;
preserve them. No commits or deployment performed.

## 2026-10-21 continuation: basket recovery milestone

Inspected existing changes and resumed the unfinished shared basket executor;
all pre-existing runtime and unrelated modifications were preserved.

Work already present but NOT yet fully validated or wired into app.py:
- trade_protected_execution.py basket REVIEW/countdown, durable BUY intents,
  reconciliation, renewed approval per SELL, short-first staged exits.
- nifty_options_engine/ticket.py executable quote/master/portfolio/monthly/margin checks.
- nifty_options_engine/service.py market context, saved reviews, fill-ledger syncing,
  fresh entry and reducing-exit approval.
- nifty_options_engine/analytics.py actual-fill strategy/monthly calculations.
- ledger.py strategy history reader and config.py quote/cost defaults.
These modules are unfinished integration work, not a completed user-facing tab.

This milestone:
- Fixed interrupted iron-condor SELL continuation. After reconciliation confirms
  all hedges filled, only NOT_SUBMITTED short legs may resume, each with renewed
  server approval. Previously submitted legs are never retried; unresolved
  submissions remain blocked. Existing compare-and-swap persistence is retained.
- Added tests/test_nifty_basket_execution.py, using temporary SQLite and in-memory
  brokers only. PAPER lifecycle includes short close followed by hedge close.
- Seven focused basket tests passed (0.68s): countdown/ack/BUY-only persistence,
  condor resumed approval without duplicate SELL, unknown submission blocking,
  two-stage exits, symbol reservations, accepted unfilled and partial hedge blocks.
  Command: python -m pytest tests/test_nifty_basket_execution.py -q -p no:cacheprovider --basetemp=tmp/nifty-basket-fill-check

Next incomplete work (do not rebuild foundation):
1. Extend basket recovery for terminal rejected/partially filled entries and exits;
   validate structure and ownership before allowing cleanup. Never blindly retry.
2. Test service fresh risk approval, ticket guards, fill sync and analytics using
   temporary databases/mocked market data, without importing app.py.
3. Add requested separate Nifty 2.0 tab, saved review/countdown/explicit GO,
   execution reconciliation and renewed SELL acceptance, visible risk/analytics.
   Apply existing account/profile, TEST mode, live acknowledgement and risk guards.
4. Historical imports/fee reconciliation, profit-capture/exit scheduler lifecycle,
   complete monthly charts and scaling evidence remain unfinished.
LIVE entries remain blocked at the legacy NIFTY boundary. No live broker orders
were placed, modified or cancelled; runtime databases/settings were not edited.

Compatibility validation for the basket recovery milestone:
- tests/test_nifty_basket_execution.py (initial five cases) plus
  tests/test_protected_execution.py: 26 passed in 181.69s. Existing TRADE checks
  include concurrency, missing/disposed hedges, fill identity and AST-extracted
  renewed approval. No app import or live client calls.
- The final seven-case basket file passed separately as recorded above.
- Syntax compilation passed for trade_protected_execution.py and NIFTY ticket,
  service, analytics, ledger and config. Syntax alone does not validate their
  unfinished integration; further targeted service/analytics tests are required.

## 2026-10-21 continuation: ticket and entry-service validation

Inspected checkpoint/request and git status; preserved existing modifications.
- Added tests/test_nifty_ticket_service.py using synthetic master/quotes and
  temporary SQLite. No app.py import or broker client/network use.
- Found and fixed ticket max-loss display omitting estimated execution costs.
  Canonical portfolio cap already includes these costs. The ticket now displays
  strategy payoff loss plus estimated costs, and approve_entry compares the
  refreshed cost-inclusive loss to the same reviewed amount.
- Added server-side checks for enabled=false and allowed_strategies settings.
- Verified fresh quote/depth/margin/monthly/LIVE gates, master quantity, executable
  credit, durable duplicate-safe PAPER fill sync, PAPER/LIVE ledger separation,
  actual hedge-cost reapproval and monthly lock changes after review.
- Initial focused run: 1 failed, 7 passed; failure exposed the cost-display issue.
  After fixes and additional guards: 18 passed in 0.94s across ticket/service and
  basket tests. Command:
  python -m pytest tests/test_nifty_ticket_service.py tests/test_nifty_basket_execution.py -q -p no:cacheprovider --basetemp=tmp/nifty-ticket-settings-check

Still incomplete: terminal partial/rejected cleanup, broader exit ownership
validation, analytics fixtures and fee/import reconciliation, app routes/separate
Nifty 2.0 tab with explicit review/GO and renewed SELL approval, scheduler lifecycle.
The market-context adapter and service/UI integration still require isolated tests;
the above is not end-to-end app acceptance. No runtime DB/settings were edited.

## 2026-10-21 milestone: separate Nifty 2.0 tab and PAPER execution window

Implemented in existing app; no replacement server:
- app.py adds Nifty 2.0 profile-aware tab/navigation, authenticated GET /nifty-2
  and POST /nifty-2/{preview,review,start,reconcile,confirm-sell,close-shorts,close-hedges}.
- New nifty_options_engine/page.py orchestrates existing ticket, durable executor,
  risk, ledger and analytics services. Only saved server-side reviews authorize
  execution; client prices/account/credentials cannot override the saved record.
- New nifty_options_engine/ui.py renders four sections: market/risk, ticket,
  execution window, monthly analytics. PE/CE/condor; expiry/current master lots;
  default two lots and nearest 300-point cover; mode; explicit checks; credit,
  costs/net max profit/cost-inclusive max loss/portfolio risk/margin; review
  countdown and acknowledgement; per-leg orders/fills; separate short/hedge exits.
- Profile-specific client is bound to saved Kite credentials for current data.
  NIFTY permission checked before market access; execution POST bypasses legacy
  form-to-environment mutation. TEST-mode check retained.
- PAPER uses the existing KiteBrokerAdapter with paper_trading=True; no live
  client is constructed for order submission. LIVE is explicitly preview-only
  at an unoverrideable server boundary pending remaining live integration checks.
- Analytics uses saved strategy fills only, identifies PAPER zero simulated fees,
  displays unknown charges/marks honestly, gross/net/open MTM, completed spreads,
  win/loss statistics, hedge costs, strategy table and daily realised table.
  POP is explicitly unavailable pending a validated model; no invented probability.

Validation:
- New tests/test_nifty_page.py executes saved-review -> countdown -> BUY ->
  reconciliation -> renewed SELL -> reconciliation -> short exit -> hedge exit
  -> CLOSED, checks ledger/P&L, account ownership, explicit ack, LIVE block before
  adapter creation, HTML escaping and real market-context adapter with synthetic
  Kite responses and temporary repositories.
- 22 focused tests passed in 2.45s across test_nifty_page.py,
  test_nifty_ticket_service.py and test_nifty_basket_execution.py:
  python -m pytest tests/test_nifty_page.py tests/test_nifty_ticket_service.py tests/test_nifty_basket_execution.py -q -p no:cacheprovider --basetemp=tmp/nifty-window-final
- app/page/UI syntax verified without app import; git diff --check passed with
  existing line-ending warnings. No full suite or application scheduler startup.
- No live orders placed/modified/cancelled, no runtime settings/DB edits in tests.

Access after restarting the existing app: /nifty-2 (default localhost port 8765),
Nifty 2.0 tab beside Nifty Income. Enable Nifty Income for the selected profile in
Kite Setup and connect current Kite data. Use PAPER; Refresh preview, Save order
review, wait countdown, acknowledge, GO (BUY only), Reconcile, acknowledge SELL,
Reconcile. Explicit exits close shorts before hedge disposal.

Remaining acceptance work (do not describe overall NIFTY 2.0 as complete):
- LIVE entry regime/event/monthly-source validation and profile/session identity
  end-to-end checks; retain hard live-preview block until those are implemented.
- Recovery for terminal partial/rejected orders and robust exit ownership checks.
- Reviewed historical imports/fee attribution, automated profit/time/emergency
  exit lifecycle, full charts/scaling evidence and configurable settings UI.
- Browser visual verification has not been performed. Tests cover rendering and
  isolated controller lifecycle, not full running-server/browser acceptance.

## 2026-10-21 milestone: Nifty Income guarded market execution

Supersedes the prior LIVE-preview-only checkpoint; the default remains LIVE off.
Human requested the execution page be Nifty Income and support market placement.

- Renamed the new execution tab/page Nifty Income. GET /nifty-income and /nifty-2
  open it; old dashboard preserved at /nifty-income/legacy as Nifty Income Legacy.
- Added explicit LIVE permission form using existing NIFTY config persistence.
  No runtime setting was changed by development/tests. Existing Kite Setup
  KITE_CONFIRM_LIVE_ORDER=YES is also mandatory for submissions.
- Replaced rollout-only blocker with server-side LIVE gates. Every real submission
  requires typed PLACE LIVE ORDERS plus acknowledgement. Persisted review,
  configured countdown, verified BUY fills, fresh risk/quotes/margin/monthly
  checks, account ownership and symbol reservation remain mandatory.
- Broker client is bound to saved selected-profile credentials. Account identity
  from Kite profile() is hashed and bound to the review; changed account blocks
  both submission and reconciliation. Existing KiteBrokerAdapter is reused with
  the bound client/account, retaining its monthly pre-order risk check.
- Existing fresh NIFTY no-trade/regime/event, data-quality, confidence sizing,
  allocation/layer and strategy-selection vetoes are retained through
  live_snapshot_gate. Missing results fail closed. Requested lots must obey
  FULL_SIZE/HALF_SIZE allowance, and structure must match existing approval.
  Quotes are age-checked after the potentially lengthy legacy risk refresh.
- LIVE execution action logs contain only action/mode/state/generated execution
  ID, never broker credentials, tokens or personal account details.
- Fixed partial-fill risk pricing: actual filled quantity plus saved LIMIT for
  remaining quantity, rather than assigning partial average to the entire leg.
- Strengthened LIVE exit checks: exact remaining strategy ownership and broker
  quantity, no conflicting orders, and no uncovered shorts before hedge disposal.
  Unresolved ownership/partial rejection remains blocked for manual reconciliation;
  this release does not blindly retry, modify or cancel broker orders.
- UI labels LIVE real orders, provides typed confirmation for entry/SELL/exits,
  and retains PAPER workflow. Orders remain LIMIT, not unpriced MARKET orders.

Validation: 35 focused tests passed across tests/test_nifty_live_execution.py,
 test_nifty_page.py, test_nifty_ticket_service.py, test_nifty_basket_execution.py.
New LIVE-flow tests exclusively use an in-memory exchange: accepted/partial
hedges blocked, confirmed fills -> SELL, short-first exit -> hedge exit, renewed
regime/monthly/permission checks, TEST blocking, account changes, missing hedge,
confidence sizing and structure vetoes. No real broker APIs/orders in testing.
Syntax checks and git whitespace checks performed without importing app.py.

Use after restarting app: Nifty Income -> connect selected profile in Kite Setup
-> explicit live acknowledgement -> enable LIVE permission in page -> select
LIVE -> refresh preview -> resolve every block -> save review -> wait countdown
-> acknowledge/type confirmation -> GO (BUY only) -> reconcile actual fills
-> renew acknowledgement/type confirmation -> submit covered SELL -> reconcile.
An order receipt means pending, not filled. Existing NIFTY vetoes may block a
chosen trade; no manual override was introduced.

Outstanding broader NIFTY 2.0 work: reviewed historical imports/fee attribution,
partial/rejected recovery UI, automatic exits/profit capture, full charts/scaling
and running-browser visual acceptance. No actual market execution was tested.
