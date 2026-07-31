from __future__ import annotations

from ..models.governance_snapshot import GovernanceSnapshot, GovernanceStatus


RED_FLAG_TERMS = {
    "auditor_resignation",
    "qualified_audit_opinion",
    "regulatory_action",
    "use_of_proceeds_deviation",
    "promoter_share_sale",
}


def analyze_governance(snapshot: GovernanceSnapshot) -> GovernanceSnapshot:
    if not snapshot.has_data:
        return snapshot.model_copy(update={"status": GovernanceStatus.DATA_PENDING})
    material_flags = {flag for flag in snapshot.flags if flag not in snapshot.immaterial_flags}
    pledge = snapshot.promoter_pledge
    pledge_change = snapshot.pledge_change_qoq
    if material_flags & RED_FLAG_TERMS or (pledge is not None and pledge > 5) or (
        pledge_change is not None and pledge_change > 0.5
    ):
        status = GovernanceStatus.RED
    elif material_flags or (snapshot.promoter_change_qoq is not None and snapshot.promoter_change_qoq < -1):
        status = GovernanceStatus.YELLOW
    else:
        status = GovernanceStatus.GREEN
    return snapshot.model_copy(update={"status": status})
