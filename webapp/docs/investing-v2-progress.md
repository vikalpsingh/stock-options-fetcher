# Investing Decision Engine v2 — architecture and checkpoint

## Scope and approved portfolio source
Keep the existing configured Investing portfolio (user confirmed). Quantities and cost come from existing Investing rows, not live Kite holdings. Quotes continue through existing Kite caching. No order action belongs to this engine.

## Architecture inspection
- Application uses `KiteWebHandler`/Python HTTP routing, not Flask. Preserve `/investing`, `/investing/load`, `investing_holdings_rows`, and `render_investing_panel`.
- `investing_holdings_rows` uses `INVESTING_HOLDINGS` plus `investing_resolved_quote_candidates`, `cached_kite_instruments`, and `cached_kite_quote`. Current fundamentals are placeholders. No verified financial provider was found in this flow.
- Existing `investing_52_week_levels` fallback does not establish adjusted-price provenance; it must not silently qualify long-horizon returns for the new engine.
- Existing SQLite repositories use explicit connection/transaction boundaries. Reuse that convention and the supplied application database path; never initialize a production database on module import.
- Existing `ipo_evaluation/gpt/openai_client.py` demonstrates injected OpenAI client, Structured Outputs and bounded retries; its IPO-specific schema/prompt cannot be reused as investment decisions. A future adapter should use the same server-side credentials and an investing-specific schema, without importing app.py.
- Existing scheduled jobs include broker execution. Do not attach research jobs to order-placement jobs. Background research job persistence/lifecycle still needs a dedicated design checkpoint before UI dispatch.
- Existing UI uses env_hidden_fields_for_render. Audit rendered credential fields before new UI integration; do not copy credential-bearing fields to new forms or GPT payloads.

## Implemented checkpoint: data foundation
New additive package `investing/`:
- config.py: INVESTING_V2_ENABLED defaults false; data model version.
- schemas.py: typed metric observation, provenance/period/unit/confidence validation, explicit evidence states, no look-ahead at evaluation time.
- fundamentals.py: injected provider protocol, CSV/JSON import; no network adapter or fabricated endpoints. Complete batch validation precedes persistence.
- market_data.py: configured portfolio adapter with ISIN/exchange matching, ambiguity detection, unknown weights when any holding valuation is unknown; corporate-action-adjusted history prerequisite.
- repository.py: account-scoped append-only SQLite evidence and evaluation snapshots, content-hash deduplication and model versions. Schema creation explicit only.
- service.py: disabled-by-default import facade; no HTTP registration, Kite, GPT or order side effects.
- Tests: tests/test_investing_data_v2.py.

`VERIFIED` in a manual import is the importer's evidence assertion, not independent vendor authentication. Source citations must be reviewed before enabling recommendations. ISIN syntax validation does not prove company identity; adapter requires supplied verified master mapping and rejects ambiguity. Current Kite metadata must not be assumed to provide ISIN for every configured holding.

## Minimal future integration points
1. Existing portfolio load supplies configured rows to read-only adapter with verified identity mappings.
2. Feature-gated new module renders additional columns/details within existing table; preserve old columns and refresh action.
3. Explicit import/re-evaluation actions dispatch only to investing service, never generic trading handlers.
4. GPT only on explicit evaluation/meaningful version change, not GET or price refresh.
5. Pass account scope on server; no account credentials in evidence or AI prompts.

## Remaining sequence
1. Build verified identity mapping/import UI and canonical latest-observation selection with conflicting-source handling.
2. Sector-specific metric applicability, configurable thresholds/units, deterministic scores and NOT_RATABLE prerequisites. All 10 sector models need boundary fixtures before acceptance.
3. Risk overrides, defensible valuation/MOS, fundamental view separate from concentration action; independent confidence.
4. Thesis history/deltas, evidence versions and quarterly/event snapshots; schema is ready but evaluator not implemented.
5. Optional structured GPT reviewer with source references, cache/timeout/token limits and disagreement handling.
6. Persistent read-only job orchestration, progress/errors and feature-gated UI filters/modal/summary cards.
7. Credential-field audit, refresh regression checks, browser validation and opt-in acceptance.

## Risks / unresolved inputs
- No real verified fundamentals batch or confirmed ISIN mapping has been supplied. Actual holdings are NOT_RATABLE until these are available; no scores or investment advice have been invented.
- No verified corporate-action-adjusted history provider is connected. Long-horizon returns remain unavailable without explicit adjusted input.
- Feature stays disabled; current Investing routes/UI are untouched. Setting the flag alone does not expose UI at this checkpoint.
- No production/runtime SQLite files, credentials, existing portfolio settings or broker operations were touched.

## Validation
`python -m pytest tests/test_investing_data_v2.py -q -p no:cacheprovider --basetemp=tmp/investing-data-v2`
Result: 14 passed. Temporary SQLite only; no network or app.py import.
Checks cover disabled no-side-effects, invalid metadata/nonfinite values, timezone and period sequencing, evidence freshness, point-in-time visibility, CSV/JSON equivalence, atomic batches, duplicate/restart/account isolation, snapshots, configured quantities, ambiguous identity, missing marks and adjusted-history requirement.

This is the first independently testable data checkpoint, not full engine/UI completion.

## 2026-10-24 — Scoring, optional GPT and existing-table integration
Implemented additive modules: sector_models.py, scoring.py, ai_review.py, jobs.py, ui.py, integration.py. app.py has only rendering/HTTP integration seams plus removal of hidden credentials from the Investing form. Existing configured portfolio/price refresh remains authoritative.

- Ten versioned sector models with bounded, unit-aware weighted scores; thresholds can be overridden in evaluate(..., thresholds=...). Overrides and allocation limits are saved in results. Generic governance/entry/pipeline quality fields are sourced analyst assessments on a documented score_100 scale, not inferred financial facts. Sector models are initial configurable research policies, not calibrated return predictors.
- Missing/stale/wrong-unit essential data produces NOT_RATABLE/REVIEW. Explicit NOT_APPLICABLE guidance/visibility changes applicability denominators without awarding missing-data points. Conflicting same-period observations require review. No P&L input enters quality scoring.
- BUY needs score >=80, confidence >=65, supported MOS >=20%, acceptable peer valuation, intact/improving thesis and no material risk flags. Governance allegations cause REVIEW; adequate-confidence confirmed critical issues permit SELL/EXIT. Low score alone never triggers SELL.
- Company 7% / sector 25% default add ceilings; unknown weights prohibit adds. Current source has no correlated-business exposure mapping, so correlated-group limits are not implemented. Allocation targets remain advisory; no order APIs are imported or invoked.
- Persistence keeps versioned score/evidence/thesis-status snapshots; changes of >=5 points against the previous snapshot affect thesis trend. Full user-authored rationale/catalyst/invalidation editing is not implemented; explicit verified thesis flags and evidence are currently required.
- Explicit background evaluation jobs persist progress and per-symbol failures in SQLite. One active job per account; stale interrupted work becomes INTERRUPTED after two hours when another request is made. Interrupted work is not automatically retried. This lightweight daemon-thread implementation does not guarantee jobs complete across process restarts; completed snapshots persist.
- Optional OpenAI Responses strict JSON schema, server credentials, 30s timeout, one SDK retry, 1600-token cap; cached by full safe evidence/decision package + prompt version. No GPT on page load/price refresh. Failure fallback leaves deterministic result unchanged. Commentary references must name supplied metrics; prose claims still need human review. No API request was made in validation.
- Existing table gains Score, Confidence, Growth, Quality, Valuation, Guidance, Thesis, Portfolio %, Decision. Details dialog includes components, source/period, warnings, suggestions, GPT explanation and history. Filters include DATA INCOMPLETE; sort options include score, weight, valuation, growth, correction. Research controls support refresh, import and selected/all evaluation; progress is refreshed manually.
- Old (>24h) results show REVIEW/NO_ACTION; materially changed current weights also require a new evaluation. Source imports should always be followed by explicit re-evaluation. Existing snapshots remain history, not live trade approvals.

### Enabling / usage
The feature remains disabled by default as requested. Set the server environment variable `INVESTING_V2_ENABLED=true`, restart the application, open Investing and refresh the configured portfolio. No runtime settings were edited by this implementation.
Use the manual evidence panel to paste CSV/JSON with all Observation fields documented in investing/schemas.py. Verify source and ISIN/exchange identity, select the confirmation checkbox, then import. Sector values must exactly match a model in investing/sector_models.py. Model definitions specify required metric names, units and thresholds. Dates/timestamps and source metadata are mandatory. Missing values use null + MISSING; do not substitute zero. Keep GPT unchecked unless an explicit paid review is wanted and OPENAI_API_KEY is configured server-side.
No vendor fundamentals or corporate-action-adjusted history feed has been invented or connected; holdings remain REVIEW until enough verified data is imported.

### Validation
32 focused tests passed across tests/test_investing_data_v2.py and tests/test_investing_engine_v2.py (mocked GPT, temporary SQLite, no app import/network/orders). Python source compilation passed for app.py and investing package. Tests cover all ten models, bounds, missing/stale/conflicting data, units, applicability, valuation gates, governance overrides, concentration, confidence, thesis transitions, GPT cache/disagreement/failure, account isolation, background persistence, escaping, disabled behavior and preservation of original table cells.
Browser visual QA, live-provider integration and production enablement were not performed. No full test suite or live orders were run.

## 2026-10-25 — Kite Setup toggle
Investing v2 is now controlled by Kite Setup → Investing Decision Engine → Enable Investing v2 scoring and research → Save Kite Setup. Saved `investing_v2_enabled` overrides the legacy environment flag (including saved OFF). Environment fallback is retained only until a setting is saved, preserving existing installations. Rendering, evaluation and import use the same saved setting. Changes apply on the next request without restarting. No runtime setting was changed during implementation.
Validation: 34 focused Investing tests passed, including saved ON/OFF precedence and unchecked/absent checkbox behavior.

## Evaluation data-path fix
Read-only inspection found zero investing_v2_evidence rows in the local database, including SCHNEIDER, PGEL and SHAILY. Missing evidence previously raised a generic failure and never persisted a table result. Added explicit resolution diagnostics and account/exchange-scoped current outcome storage, including NOT_RATABLE outcomes without fabricated ISINs. Outcomes survive subsequent selected-stock jobs and recover after verified evidence import. Lowercase supported model names normalize; descriptive/unknown models and conflicting identities remain explicit blocks. Unexpected errors expose only exception type and filename/line, never exception payloads. Existing snapshot history remains intact. No runtime database or settings were modified during inspection/testing.
Validation: 35 focused tests passed, including all three reported symbols, import-to-score recovery, persistence, account isolation, exchange/model/identity failures and safe engine diagnostics. No fundamentals vendor was added; sourced manual imports remain required for real scores.

## Custom GPT handoff and compact P&L
P&L now uses the existing lakh formatter with raw rupee sort value and exact amount tooltip. Added investing/advisor_handoff.py for an explicit user-driven custom GPT workflow: select one/all configured holdings, copy the requested stock/quantity/average-buy/CMP prompt, open the user's Indian Stock Advisor URL, then paste/save its response to display on Investing. The custom GPT website has no direct API callback to this application; this is not an automatic response integration. No portfolio data is placed in the URL or sent automatically. Only requested holding fields enter the prompt; account credentials are excluded. Saved responses are account-scoped escaped text, clearly marked unverified commentary, and never modify engine decisions or order state.
Validation: 21 focused tests passed (handoff, escaping/account persistence, prompt allowlist, lakh formatting and existing engine UI). Source compilation verified separately. No actual GPT submission, broker operation or runtime DB write during testing.
