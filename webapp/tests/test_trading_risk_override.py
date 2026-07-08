from app import (
    apply_soft_risk_override_to_decision,
    risk_decision_soft_override_allowed,
)


def test_soft_override_allows_only_named_risk_codes():
    decision = {
        "decision": "BLOCKED",
        "risk_score": 30,
        "reason_codes": [
            "LOW_PREMIUM_YIELD",
            "MISSING_TECHNICAL_DATA",
            "MISSING_MARKET_DATA",
        ],
    }
    assert risk_decision_soft_override_allowed(decision)


def test_soft_override_rejects_hard_risk_codes():
    decision = {
        "decision": "BLOCKED",
        "risk_score": 30,
        "reason_codes": ["LOW_PREMIUM_YIELD", "EVENT_RISK"],
    }
    assert not risk_decision_soft_override_allowed(decision)


def test_soft_override_changes_decision_to_approved_but_keeps_audit_reason():
    order = {"quantity": 750}
    decision = {
        "decision": "BLOCKED",
        "risk_score": 30,
        "reason_codes": ["LOW_PREMIUM_YIELD"],
        "human_reason": "Risk engine blocked trade: LOW_PREMIUM_YIELD",
    }
    overridden = apply_soft_risk_override_to_decision(order, decision)
    assert overridden["decision"] == "APPROVED"
    assert overridden["original_decision"] == "BLOCKED"
    assert overridden["soft_override_applied"] is True
    assert overridden["recommended_quantity"] == 750
    assert "LOW_PREMIUM_YIELD" in overridden["human_reason"]
