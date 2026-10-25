"""Explicit evidence resolution; missing fundamentals are a result, not a crash."""
from .sector_models import REPLACEMENTS

class EvidenceIssue(ValueError):
    def __init__(self,code,reason):
        super().__init__(reason)
        self.code=code
        self.reason=reason


def resolve(observations,symbol,exchange):
    symbol=symbol.strip().upper();exchange=exchange.strip().upper()
    matches=[o for o in observations if o.symbol.strip().upper()==symbol and o.exchange.strip().upper()==exchange]
    if not matches:
        elsewhere=any(o.symbol.strip().upper()==symbol for o in observations)
        if elsewhere:raise EvidenceIssue('EXCHANGE_MISMATCH','Fundamentals exist for a different exchange. Verify the configured exchange and imported ISIN mapping; records are not automatically reassigned.')
        raise EvidenceIssue('FUNDAMENTALS_MISSING','No sourced fundamentals are imported for this stock. Live CMP does not include company financials. Open Refresh fundamentals, import verified CSV/JSON observations with ISIN and sector model, then re-evaluate.')
    if len({o.isin for o in matches})!=1:
        raise EvidenceIssue('IDENTITY_CONFLICT','Multiple ISINs match this symbol and exchange. Correct the imported company mapping before evaluation.')
    sectors={o.sector.strip().upper().replace(' ','_').replace('-','_') for o in matches}
    if len(sectors)!=1:
        raise EvidenceIssue('MODEL_CONFLICT','Imported observations disagree on sector model. Resolve the model before evaluation.')
    sector=next(iter(sectors))
    if sector not in REPLACEMENTS:
        raise EvidenceIssue('SECTOR_MODEL_REQUIRED','Imported sector must identify a supported scoring model: '+', '.join(REPLACEMENTS)+'. Descriptive portfolio sector labels are not scoring models.')
    return matches,matches[0].isin,sector


def review_result(symbol,exchange,code,reason,now):
    from .scoring import VERSION
    return dict(symbol=symbol,exchange=exchange,status='NOT_RATABLE',decision='REVIEW',portfolio_action='NO_ACTION',
        score=None,confidence=0,data_coverage=0,component_scores={},evidence=[],warnings=[reason],
        diagnostic_code=code,valuation='UNKNOWN',thesis_status='UNKNOWN',evaluated_at=now.isoformat(),model_version=VERSION)
