from trade_workflow import TradeWorkflowRepository, score_discipline


def test_draft_is_account_scoped_and_preserves_process(tmp_path):
    repo = TradeWorkflowRepository(tmp_path / "workflow.db")
    draft = repo.create("acct-a", "TCS", {"scan_date": "2026-10-18"})
    assert repo.get(draft["draft_id"], "acct-b") is None
    updated = repo.update(
        draft["draft_id"], "acct-a", stage="chart",
        changes={"hypothesis": "BEARISH_RESISTANCE_REJECTION", "discipline": {"screened": True, "evidence_reviewed": True}},
    )
    assert updated["stage"] == "chart"
    assert updated["version"] == 2
    assert updated["data"]["hypothesis"] == "BEARISH_RESISTANCE_REJECTION"


def test_good_decision_loss_is_not_poor_decision():
    result = score_discipline(
        {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 15},
        hard_violation=False, outcome="LOSS",
    )
    assert result["score"] == 100
    assert result["classification"] == "GOOD DECISION — LOSS"


def test_profitable_risk_violation_is_poor_decision():
    result = score_discipline(
        {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 15},
        hard_violation=True, outcome="PROFIT",
    )
    assert result["band"] == "Needs improvement"
    assert result["classification"] == "POOR DECISION — PROFIT"


def test_open_trade_is_provisional_and_no_trade_is_supported():
    open_result = score_discipline(
        {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 0},
        hard_violation=False, outcome="OPEN",
    )
    assert open_result["classification"] == "PROVISIONAL PROCESS ASSESSMENT"
    no_trade = score_discipline(
        {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 15},
        hard_violation=False, outcome="NO_TRADE",
    )
    assert no_trade["classification"] == "GOOD NO-TRADE DECISION"
