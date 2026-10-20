from trade_opportunity_engine import (
    TradeOpportunityRepository,
    assess_live_entry,
    liquidity_state,
    premarket_score,
    terminal_otm_probability,
)


def test_probability_is_explicit_model_not_delta_proxy():
    probability = terminal_otm_probability(122.19, 116, 38, 0.32, "PE")
    assert probability is not None
    assert 0 < probability < 100


def test_pnb_gap_and_premium_collapse_is_missed_do_not_chase():
    baseline = {
        "previous_close": 116.31,
        "option_close": 4.58,
        "minimum_credit": 3.20,
        "premarket_score": 78,
    }
    live = {
        "cmp": 122.19, "open": 122.19, "bid": 1.66, "ask": 1.70, "ltp": 1.66,
        "volume": 10000, "oi": 50000, "quote_fresh": True,
        "earnings_status": "PASS", "risk_status": "PASS", "capital_available": True,
        "probability_quality": 70, "momentum_score": 65, "capital_efficiency_score": 25,
    }
    result = assess_live_entry(baseline, live)
    assert result["gap_pct"] == 5.06
    assert result["premium_change_pct"] < -63
    assert result["status"] == "MISSED — LOW PREMIUM"
    assert any("below minimum credit" in reason for reason in result["reasons"])


def test_wide_spread_is_blocked_even_with_large_premium():
    status, reason, spread = liquidity_state(8, 10, 9, 100000, 100000)
    assert status == "BLOCK"
    assert spread > 5
    assert "fails liquidity" in reason


def test_premarket_score_does_not_normalise_against_another_candidate():
    result = premarket_score(
        technical_score=80, structure_score=75, alignment_score=70,
        model_probability=72, net_credit_yield=2.5, mandatory_complete=True,
    )
    assert result["score"] == 74.05
    assert result["status"] == "CANDIDATE"


def test_baseline_is_immutable_and_snapshots_are_versioned(tmp_path):
    repo = TradeOpportunityRepository(tmp_path / "opportunity.db")
    assert repo.save_baseline_once("A1", "2026-10-19", [{"symbol": "PNB", "cmp": 116.31}]) is True
    assert repo.save_baseline_once("A1", "2026-10-19", [{"symbol": "PNB", "cmp": 122.19}]) is False
    assert repo.baseline("A1", "2026-10-19")["rows"][0]["cmp"] == 116.31
    first = repo.save_snapshot("A1", "2026-10-19", "LIVE", [{"symbol": "PNB", "cmp": 121}])
    second = repo.save_snapshot("A1", "2026-10-19", "LIVE", [{"symbol": "PNB", "cmp": 122}])
    assert second > first
