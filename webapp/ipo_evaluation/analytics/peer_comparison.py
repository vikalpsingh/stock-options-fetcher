from __future__ import annotations

from ..models.peer_snapshot import PeerSnapshot
from .ratio_calculator import null_safe_median


PEER_METRICS = (
    "revenue_growth",
    "pat_growth",
    "operating_margin",
    "roce",
    "roe",
    "debt_equity",
    "cfo_pat",
    "debtor_days",
    "pe",
    "pb",
    "ps",
    "ev_ebitda",
)


def calculate_peer_medians(peers: list[PeerSnapshot]) -> dict[str, float | None]:
    return {
        metric: null_safe_median([peer.metrics.get(metric) for peer in peers])
        for metric in PEER_METRICS
    }
