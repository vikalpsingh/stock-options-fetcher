from __future__ import annotations

from ..models.peer_snapshot import PeerRelationship, PeerSnapshot


def select_top_peers(
    industry: str,
    business_model_subtype: str,
    candidates: list[PeerSnapshot],
    limit: int = 2,
) -> list[PeerSnapshot]:
    target_industry = industry.strip().lower()
    target_subtype = business_model_subtype.strip().lower()

    def rank(peer: PeerSnapshot) -> tuple[float, float, float, float]:
        exact_industry = peer.industry.strip().lower() == target_industry and bool(target_industry)
        exact_subtype = peer.business_model_subtype.strip().lower() == target_subtype and bool(target_subtype)
        relation = 3 if exact_industry and exact_subtype else 2 if exact_industry else 1
        return (
            relation,
            1 if peer.financial_data_available else 0,
            peer.liquidity_score or 0,
            peer.listed_track_record_years or 0,
        )

    selected = sorted(candidates, key=rank, reverse=True)[:limit]
    output: list[PeerSnapshot] = []
    for peer in selected:
        exact_industry = peer.industry.strip().lower() == target_industry and bool(target_industry)
        exact_subtype = peer.business_model_subtype.strip().lower() == target_subtype and bool(target_subtype)
        relationship = (
            PeerRelationship.EXACT_PEER
            if exact_industry and exact_subtype
            else PeerRelationship.NEAR_PEER
            if exact_industry
            else PeerRelationship.BROAD_SECTOR_REFERENCE
        )
        output.append(peer.model_copy(update={"relationship": relationship}))
    return output
