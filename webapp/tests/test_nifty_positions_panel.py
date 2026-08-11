import unittest
from unittest.mock import patch

import app


class NiftyPositionsPanelTest(unittest.TestCase):
    def test_best_positions_panel_follows_decision_gate_and_uses_existing_review_flow(self):
        candidate = {
            "side": "PE",
            "expiry_date": "2026-08-04",
            "tradingsymbol": "NIFTY2680422700PE",
            "hedge_symbol": "NIFTY2680422400PE",
            "strike": 22700,
            "nifty_spot": 24022.70,
            "otm_pct": 5.51,
            "mmi_selected_otm_pct": 5.50,
            "option_ltp": 34.65,
            "bid": 34.65,
            "ask": 35.70,
            "oi": 32175,
            "change_oi": 32175,
            "volume": 38675,
            "premium_value_per_lot": 2252.25,
            "max_gain_opportunity": 630.50,
            "margin_required": 36000,
            "credit_pct_of_spread_width": 10.0,
            "spread_width_points": 300,
            "credit_quality": "GOOD",
            "premium_yield_on_margin_pct": 1.75,
            "risk_status": "GREEN",
        }
        snapshot = {
            "config": {
                "manual_pair_sell_markup_percent": 20.0,
                "entry_time": "15:16",
                "time_exit_time": "14:59",
                "execution_mode": "SUGGESTION_ONLY",
            },
            "state": {},
            "summary": {},
            "positions": [],
            "suggestion": {
                "allowed": True,
                "pe_otm_pct": 5.5,
                "ce_otm_pct": 5.5,
            },
            "confidence_score": {"score": 80, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": []},
            "candidate_previews": [candidate],
            "warnings": [],
        }

        rendered = app.render_nifty_income_panel(
            app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot)
        )

        banner_index = rendered.index("NIFTY Command Banner")
        command_index = rendered.index("Tactical Spread Command Center")
        gate_index = rendered.index("Decision Gate")
        positions_index = rendered.index("NIFTY Candidate Preview")
        self.assertLess(banner_index, command_index)
        self.assertLess(command_index, gate_index)
        self.assertLess(gate_index, positions_index)
        self.assertEqual(rendered.count('id="nifty-pair-open"'), 1)
        self.assertIn(">Open NIFTY Order Ticket</button>", rendered)
        self.assertIn("BUY hedge near ask, then SELL short near bid/CMP", rendered)
        self.assertIn("NIFTY Order Ticket", rendered)
        self.assertIn("nifty-pair-defined-risk-ack", rendered)
        self.assertIn("I accept this defined-risk NIFTY trade", rendered)
        self.assertIn("PE spread", rendered)
        self.assertIn("BUY PE hedge + SELL PE short", rendered)
        self.assertIn('name="nifty_pair_include_cover" value="1"', rendered)
        self.assertIn('id="nifty-pair-include-cover" checked disabled', rendered)
        self.assertNotIn("Build Tactical Spread Order", rendered)

    def test_nifty_income_retired_scheduler_sections_are_hidden(self):
        snapshot = {
            "config": {
                "manual_pair_sell_markup_percent": 20.0,
                "entry_time": "15:16",
                "time_exit_time": "14:59",
                "execution_mode": "SUGGESTION_ONLY",
            },
            "state": {},
            "summary": {},
            "positions": [],
            "suggestion": {"allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
            "candidate_previews": [],
            "warnings": [],
        }

        rendered = app.render_nifty_income_panel(
            app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot)
        )

        self.assertNotIn("Due T-7 Closure Legs", rendered)
        self.assertNotIn("NIFTY Income Risk Monitor Summary", rendered)
        self.assertNotIn("Run Entry Now", rendered)
        self.assertNotIn("Run T-7 Exit Now", rendered)
        self.assertNotIn("Run Pair Monitor Now", rendered)
        self.assertNotIn("Enable T-7 time exit", rendered)
        self.assertNotIn("Enable 15-min pair exit monitor", rendered)

    def test_current_nifty_risk_rows_show_position_action_buttons(self):
        snapshot = {
            "config": {"manual_pair_sell_markup_percent": 20.0, "entry_time": "15:16"},
            "summary": {"pnl": -2882.75},
            "suggestion": {"allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
            "confidence_score": {"score": 80, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": []},
            "positions": [
                {
                    "tradingsymbol": "NIFTY2681825200CE",
                    "quantity": 195,
                    "average_price": 26.0,
                    "last_price": 3.75,
                    "pnl": -4338.75,
                    "expiry": "2026-08-18",
                },
                {
                    "tradingsymbol": "NIFTY26AUG23000PE",
                    "quantity": -130,
                    "average_price": 18.0,
                    "last_price": 6.8,
                    "pnl": 1456.0,
                    "expiry": "2026-08-25",
                },
            ],
            "candidate_previews": [],
        }

        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        self.assertIn(">Create Hedge</button>", rendered)
        self.assertIn(">Repair Spread</button>", rendered)
        self.assertIn(">Sell Against Long</button>", rendered)
        self.assertIn(">Roll + Sell</button>", rendered)
        self.assertIn("nifty-position-action-modal", rendered)
        self.assertIn("nifty-position-action-projected-pnl", rendered)
        self.assertIn("P&amp;L after hedge/order", rendered)
        self.assertIn("nifty-position-pnl-note", rendered)

    def test_nifty_income_order_log_is_visible_near_top_after_submission(self):
        snapshot = {
            "config": {"manual_pair_sell_markup_percent": 20.0, "entry_time": "15:16"},
            "summary": {},
            "suggestion": {"allowed": True, "pe_otm_pct": 4.0, "ce_otm_pct": 4.0},
            "confidence_score": {"score": 80, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": []},
            "positions": [],
            "candidate_previews": [],
        }
        state = app.PageState(
            active_tab="nifty-income",
            nifty_income_snapshot=snapshot,
            nifty_income_results=[
                {
                    "tradingsymbol": "NIFTY26AUG22600PE",
                    "status": "LIVE_SENT",
                    "order_id": "250811000001",
                    "detail": "Manual NIFTY PE/CE income pair. Kite action: placed",
                },
                {
                    "tradingsymbol": "NIFTY26AUG22900PE",
                    "status": "BLOCKED",
                    "detail": "Short leg not sent because a protective hedge order failed.",
                },
            ],
        )

        rendered = app.render_nifty_income_panel(state)

        hero_index = rendered.index("NIFTY Income Risk-Cap Cockpit")
        log_index = rendered.index("NIFTY Kite Order Log")
        cockpit_index = rendered.index("NIFTY Status Card")
        self.assertLess(hero_index, log_index)
        self.assertLess(log_index, cockpit_index)
        self.assertIn("Sent 1 | Errors 0 | Blocked 1", rendered)
        self.assertIn("250811000001", rendered)
        self.assertIn("Short leg not sent", rendered)

    def test_nifty_pair_submit_helper_copies_moved_modal_fields_to_parent_form(self):
        rendered = app.render_page(
            app.PageState(
                active_tab="nifty-income",
                nifty_income_snapshot={
                    "config": {"manual_pair_sell_markup_percent": 20.0},
                    "summary": {},
                    "suggestion": {"allowed": True, "pe_otm_pct": 4.0, "ce_otm_pct": 4.0},
                    "confidence_score": {"score": 80, "action": "FULL_SIZE"},
                    "data_quality": {"status": "GOOD", "missing_fields": []},
                    "candidate_previews": [],
                    "positions": [],
                },
            )
        ).decode()

        self.assertIn("document.getElementById('nifty-income-panel')", rendered)
        self.assertIn("copy.dataset.modalSubmitCopy = '1'", rendered)
        self.assertIn("modal.querySelectorAll('input[name], select[name], textarea[name]')", rendered)

    def test_nifty_income_retired_jobs_are_not_in_scheduler_registry(self):
        jobs = app.scheduled_job_definitions()

        self.assertNotIn("nifty_income_entry", jobs)
        self.assertNotIn("nifty_income_time_exit", jobs)
        self.assertNotIn("nifty_weekly_pair_exit", jobs)

    def test_nifty_grow_tab_is_hidden_unless_profile_flag_enabled(self):
        profiles = {name: app.blank_kite_profile(name) for name in app.KITE_PROFILE_NAMES}
        profiles["Monika"].update(
            {
                "KITE_API_KEY": "key",
                "KITE_API_SECRET": "secret",
                "KITE_ACCESS_TOKEN": "token",
                "NIFTY_INCOME_ENABLED": True,
                "NIFTY_GROW_ENABLED": False,
            }
        )

        with patch.object(app, "load_kite_profiles", return_value=profiles):
            rendered = app.render_page(app.PageState(active_tab="kite-setup", kite_profile="Monika")).decode()

        self.assertIn("Enable NIFTYGrow tab", rendered)
        self.assertIn('data-tab="nifty-income"', rendered)
        self.assertNotIn('data-tab="nifty-grow">NIFTYGrow</button>', rendered)

    def test_nifty_grow_tab_is_visible_when_profile_flag_enabled(self):
        profiles = {name: app.blank_kite_profile(name) for name in app.KITE_PROFILE_NAMES}
        profiles["Monika"].update(
            {
                "KITE_API_KEY": "key",
                "KITE_API_SECRET": "secret",
                "KITE_ACCESS_TOKEN": "token",
                "NIFTY_INCOME_ENABLED": True,
                "NIFTY_GROW_ENABLED": True,
            }
        )

        with patch.object(app, "load_kite_profiles", return_value=profiles):
            rendered = app.render_page(app.PageState(active_tab="kite-setup", kite_profile="Monika")).decode()

        self.assertIn('data-tab="nifty-grow">NIFTYGrow</button>', rendered)

    def test_strategy_risk_contract_shows_actionable_nifty_pair_execution_card(self):
        snapshot = {
            "config": {"manual_pair_sell_markup_percent": 20.0, "entry_time": "15:16"},
            "summary": {
                "spot": 24500,
                "net_credit": 90,
                "max_gain": 5850,
                "max_loss": 13650,
                "premium_yield_on_margin_pct": 42.85,
                "hedge_width_points": 300,
            },
            "suggestion": {"allowed": True, "pe_otm_pct": 5.0, "ce_otm_pct": 5.0},
            "confidence_score": {"score": 82, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": []},
            "candidate_previews": [
                {
                    "side": "PE",
                    "expiry_date": "2026-08-25",
                    "tradingsymbol": "NIFTY26AUG23300PE",
                    "hedge_symbol": "NIFTY26AUG23000PE",
                    "strike": 23300,
                    "nifty_spot": 24500,
                    "otm_pct": 4.9,
                    "option_ltp": 45,
                    "credit_pct_of_spread_width": 15,
                    "spread_width_points": 300,
                    "max_gain_opportunity": 2925,
                    "max_loss": 6825,
                    "bid": 44,
                    "ask": 45,
                    "delta": 0.12,
                },
                {
                    "side": "CE",
                    "expiry_date": "2026-08-25",
                    "tradingsymbol": "NIFTY26AUG25700CE",
                    "hedge_symbol": "NIFTY26AUG26000CE",
                    "strike": 25700,
                    "nifty_spot": 24500,
                    "otm_pct": 4.9,
                    "option_ltp": 45,
                    "credit_pct_of_spread_width": 15,
                    "spread_width_points": 300,
                    "max_gain_opportunity": 2925,
                    "max_loss": 6825,
                    "bid": 44,
                    "ask": 45,
                    "delta": 0.12,
                },
            ],
        }

        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        risk_contract_index = rendered.index("Strategy Decision &amp; Risk Contract")
        action_card_index = rendered.index("3-4 Week 4% OTM PE + CE Income Pair")
        execution_button_index = rendered.index('id="nifty-pair-open"')
        self.assertLess(risk_contract_index, action_card_index)
        self.assertLess(action_card_index, execution_button_index)
        self.assertEqual(rendered.count('id="nifty-pair-open"'), 1)
        self.assertIn('data-pe-otm="4.00"', rendered)
        self.assertIn('data-ce-otm="4.00"', rendered)
        self.assertIn('class="nifty-risk-contract-table"', rendered)
        self.assertIn("<th>Symbol / Hedge</th>", rendered)
        self.assertIn("<th>OTM %</th>", rendered)
        self.assertIn("<th>Max gain</th>", rendered)
        self.assertIn("<th>Max loss</th>", rendered)
        self.assertIn("NIFTY26AUG23300PE", rendered)
        self.assertIn("NIFTY26AUG25700CE", rendered)
        self.assertIn("Preferred hedge width: 200-300 points", rendered)
        self.assertIn(">Open NIFTY Order Ticket</button>", rendered)

    def test_nifty_command_banner_blocks_fresh_entry_when_hedge_is_critical(self):
        snapshot = {
            "config": {"manual_pair_sell_markup_percent": 20.0, "entry_time": "15:16"},
            "summary": {"pnl": -1250, "vix": 12.1},
            "suggestion": {"allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
            "confidence_score": {"score": 82, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": [], "last_refreshed_at": "11 Aug 2026 10:01 IST"},
            "hedge_integrity": {
                "status": "CRITICAL",
                "block_new_entries": True,
                "rows": [
                    {
                        "short_symbol": "NIFTY26AUG25000CE",
                        "short_quantity": 65,
                        "hedge_symbol": "",
                        "hedge_quantity": 0,
                        "quantity_match": False,
                        "expiry_match": False,
                        "hedge_status": "UNHEDGED_SHORT",
                        "action_required": "ADD_HEDGE_OR_EXIT",
                    }
                ],
            },
            "candidate_previews": [
                {
                    "side": "CE",
                    "expiry_date": "2026-08-25",
                    "tradingsymbol": "NIFTY26AUG25000CE",
                    "hedge_symbol": "NIFTY26AUG25300CE",
                    "strike": 25000,
                    "nifty_spot": 24500,
                    "otm_pct": 2.0,
                    "mmi_selected_otm_pct": 2.0,
                    "bid": 20,
                    "ask": 21,
                    "delta": 0.12,
                    "credit_pct_of_spread_width": 10,
                    "risk_status": "GREEN",
                }
            ],
        }

        audit = app.build_nifty_screen_decision_audit(snapshot)
        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        self.assertEqual(audit["final_status"], "HEDGE_REPAIR_REQUIRED")
        self.assertFalse(audit["fresh_entry_enabled"])
        self.assertTrue(audit["exit_enabled"])
        self.assertIn("NIFTY STATUS: HEDGE REPAIR REQUIRED", rendered)
        self.assertIn("New NIFTY trade preview hidden because active hedge risk is critical", rendered)
        self.assertIn("ADD_HEDGE_OR_EXIT", rendered)
        self.assertIn('id="nifty-pair-open"', rendered)
        self.assertIn(">Open NIFTY Order Ticket</button>", rendered)

    def test_nifty_unlock_panel_shows_credit_vix_and_missing_delta_gates(self):
        snapshot = {
            "config": {
                "entry_time": "15:16",
                "nifty_options_engine": {"min_credit_pct_of_spread_width": 8.0},
            },
            "summary": {"vix": 12.14, "premium_yield_on_margin_pct": 1.25},
            "suggestion": {"allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
            "confidence_score": {"score": 66, "action": "PREVIEW_ONLY"},
            "data_quality": {"status": "PARTIAL", "missing_fields": ["sell_delta"]},
            "candidate_previews": [
                {
                    "side": "PE",
                    "expiry_date": "2026-08-25",
                    "tradingsymbol": "NIFTY26AUG23000PE",
                    "hedge_symbol": "NIFTY26AUG22700PE",
                    "strike": 23000,
                    "nifty_spot": 24500,
                    "otm_pct": 6.1,
                    "mmi_selected_otm_pct": 6.0,
                    "bid": 10,
                    "ask": 11,
                    "delta": "N/A",
                    "credit_pct_of_spread_width": 5.5,
                    "risk_status": "YELLOW",
                }
            ],
        }

        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        self.assertIn("Confidence below threshold", rendered)
        self.assertIn("Credit below tactical minimum", rendered)
        self.assertIn("<strong>VIX range</strong>", rendered)
        self.assertIn(">PASS</span>", rendered)
        self.assertIn("<strong>Delta availability</strong>", rendered)
        self.assertIn("Refresh Greeks", rendered)
        self.assertIn(">Open NIFTY Order Ticket</button>", rendered)

    def test_nifty_exit_due_and_t7_rows_use_clear_close_wording(self):
        snapshot = {
            "config": {"entry_time": "15:16"},
            "summary": {"pnl": 500, "vix": 13.0},
            "positions": [{"tradingsymbol": "NIFTY26AUG25000CE", "quantity": -65}],
            "suggestion": {"allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
            "confidence_score": {"score": 80, "action": "FULL_SIZE"},
            "data_quality": {"status": "GOOD", "missing_fields": []},
            "time_exit_orders": [
                {
                    "transaction_type": "BUY",
                    "tradingsymbol": "NIFTY26AUG25000CE",
                    "quantity": 65,
                    "reason": "TIME_EXIT_T_MINUS_7",
                    "exit_date": "2026-08-18",
                    "tag": "NIFTY_T7",
                }
            ],
        }

        audit = app.build_nifty_screen_decision_audit(snapshot)
        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        self.assertEqual(audit["final_status"], "EXIT_DUE")
        self.assertIn("EXIT_DUE", rendered)
        self.assertIn("Original side", rendered)
        self.assertIn("Close action", rendered)
        self.assertIn("SELL short", rendered)
        self.assertIn("BUY to close", rendered)

    def test_nifty_market_regime_missing_dma_uses_sideways_fallback_and_router(self):
        snapshot = {
            "config": {"entry_time": "15:16"},
            "summary": {"spot": 24500, "mmi": 77.5, "vix": 12.1, "premium_yield_on_margin_pct": 1.0},
            "market_regime": {
                "mmi_regime": "GREED_OVERBOUGHT",
                "vix_regime": "NORMAL_LOW",
                "trend_regime": "SIDEWAYS",
                "rsi_14": "N/A",
                "adx_14": "N/A",
                "dma_20": "N/A",
                "dma_50": "N/A",
            },
            "suggestion": {"allowed": False, "selected_strategy": "NO_TRADE", "skip_reason": "REGIME_BLOCK"},
            "confidence_score": {"score": 65, "action": "PREVIEW_ONLY"},
            "data_quality": {"status": "CACHED", "missing_fields": []},
            "candidate_previews": [],
        }

        audit = app.build_nifty_screen_decision_audit(snapshot)
        rendered = app.render_nifty_income_panel(app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot))

        self.assertEqual(audit["data_source"], "CACHED")
        self.assertIn("Cached data - refresh before action", rendered)
        self.assertIn("SIDEWAYS_FALLBACK", rendered)
        self.assertIn("RSI/ADX/DMA unavailable", rendered)
        self.assertIn("NIFTY blocked. Do not force trade", rendered)
        self.assertIn("Capital Router", rendered)


if __name__ == "__main__":
    unittest.main()
