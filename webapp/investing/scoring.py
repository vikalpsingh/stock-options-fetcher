"""Pure evidence evaluation; no network, credentials, database or order imports."""
import hashlib
import json
from .sector_models import model

VERSION='investing-v2.0-rules-1'


def latest(observations,now):
    by_metric={};warnings=[]
    for item in observations:
        if item.state_at(now)=='MISSING':continue
        by_metric.setdefault(item.metric,[]).append(item)
    result={}
    for metric,rows in by_metric.items():
        period=max(x.period_end for x in rows)
        rows=[x for x in rows if x.period_end==period]
        if len({(x.value,x.unit,x.status) for x in rows})>1:
            warnings.append('Conflicting evidence: '+metric);continue
        item=max(rows,key=lambda x:x.fetched_at)
        if item.state_at(now,max_period_age_days=150 if metric.startswith('quarterly_') else 450)=='VERIFIED':result[metric]=item
        else:warnings.append('Stale/not applicable: '+metric)
    return result,warnings


def evaluate(observations,sector,now,*,weight=None,sector_weight=None,previous=None,thresholds=None,company_limit=7,sector_limit=25):
    if not 0<company_limit<=100 or not 0<sector_limit<=100:raise ValueError('Invalid allocation limits')
    evidence,warnings=latest(observations,now)
    components={name:0.0 for name in ('Growth','Quality','Strength','Valuation','Governance','Entry')}
    used=[];covered=0;details=[]
    not_applicable={x.metric for x in observations if x.state_at(now)=='NOT_APPLICABLE'}
    applicable_max={name:0 for name in components}
    maximum={name:0 for name in components}
    rules=model(sector,thresholds)
    for component,metric,points,unit,bad,good in rules:
        item=evidence.get(metric)
        maximum[component]+=points
        if metric not in not_applicable:applicable_max[component]+=points
        points_scored=None
        if item and item.unit==unit:
            points_scored=round(points*max(0,min(1,(item.value-bad)/(good-bad))),2)
            if component=='Entry' and not (evidence.get('thesis_intact') and evidence['thesis_intact'].value==1):points_scored=0
            components[component]+=points_scored;covered+=points;used.append(item)
        elif metric not in not_applicable:warnings.append('Missing or wrong unit: '+metric)
        details.append(dict(component=component,metric=metric,maximum=points,score=points_scored,unit=unit,
            value=item.value if item else None,source=item.source if item else None,period=item.period_end if item else None))
    applicable_total=sum(applicable_max.values())
    covered=round(covered/applicable_total*100,1) if applicable_total else 0
    for component in components:
        if applicable_max[component]:components[component]=round(components[component]*maximum[component]/applicable_max[component],2)
    def value(key,unit=None):
        item=evidence.get(key)
        return item.value if item and (unit is None or item.unit==unit) else None
    # Independent availability groups: observations, not portfolio gain/loss.
    groups=[(25,[r[1] for r in rules if r[0] in {'Quality','Strength'}]),(25,['quarterly_revenue_growth']),
            (20,['guidance_growth']),(10,['market_fresh']),(10,['events_reviewed']),(10,[r[1] for r in rules if r[0]=='Valuation'])]
    groups=[(points,[k for k in names if k not in not_applicable]) for points,names in groups]
    groups=[(points,names) for points,names in groups if names]
    confidence=round(sum(points*sum(evidence[k].confidence/100 for k in names if k in evidence)/len(names) for points,names in groups)/sum(p for p,_ in groups)*100,1) if groups else 0
    essential=[next(r[1] for r in rules if r[0]=='Growth'),next(r[1] for r in rules if r[0]=='Quality')]
    ratable=covered>=65 and all(k in evidence and evidence[k].unit==next(r[3] for r in rules if r[1]==k) for k in essential) and not any(w.startswith('Conflicting') for w in warnings)
    score=round(min(100,sum(components.values())),1) if ratable else None
    flags=[]
    for key in ('fraud_confirmed','auditor_issue_confirmed','regulatory_restriction','thesis_broken','business_deterioration','debt_deterioration','guidance_repeated_misses'):
        if value(key,'boolean')==1:
            item=evidence[key];flags.append(dict(severity='CRITICAL',metric=key,source=item.source,date=item.filing_date))
    if value('governance_allegation','boolean')==1:flags.append(dict(severity='REVIEW_REQUIRED',metric='governance_allegation',source=evidence['governance_allegation'].source))
    if (value('promoter_pledge','percent') or 0)>=50:flags.append(dict(severity='REVIEW_REQUIRED',metric='promoter_pledge',source=evidence['promoter_pledge'].source))
    thesis='BROKEN' if value('thesis_broken','boolean')==1 else 'INTACT' if value('thesis_intact','boolean')==1 else 'UNKNOWN'
    if thesis=='INTACT' and previous and score is not None and previous.get('score') is not None:
        delta=score-previous['score'];thesis='IMPROVING' if delta>=5 else 'WEAKENING' if delta<=-5 else thesis
    ratio=value('sector_valuation_ratio','ratio')
    valuation='UNKNOWN' if ratio is None or ratio<=0 else 'CHEAP' if ratio<0.7 else 'ATTRACTIVE' if ratio<0.9 else 'FAIR' if ratio<=1.2 else 'EXPENSIVE' if ratio<=2 else 'EXTREME'
    # MOS is imported only with a sourced defensible-model observation, never inferred from correction.
    mos=value('margin_of_safety','percent') if value('valuation_model_supported','boolean')==1 else None
    decision='REVIEW'
    if ratable and confidence>=65:
        if any(f['severity']=='REVIEW_REQUIRED' for f in flags):decision='REVIEW'
        elif any(f['severity']=='CRITICAL' for f in flags):decision='SELL'
        elif score>=80 and valuation in {'CHEAP','ATTRACTIVE','FAIR'} and mos is not None and mos>=20 and thesis in {'INTACT','IMPROVING'}:decision='BUY'
        elif score>=65 and thesis in {'INTACT','IMPROVING'}:decision='HOLD'
    concentration=weight is None or sector_weight is None or weight>=company_limit or sector_weight>=sector_limit
    action='EXIT' if decision=='SELL' else 'ADD_SMALL' if decision=='BUY' and not concentration else 'HOLD' if decision in {'BUY','HOLD'} else 'NO_ACTION'
    if concentration:warnings.append('NO ADD: concentration limit or incomplete portfolio weights. Advisory rebalance review only.')
    data_version=hashlib.sha256(json.dumps([x.to_dict() for x in sorted(observations,key=lambda x:(x.metric,x.source,x.fetched_at))],sort_keys=True).encode()).hexdigest()
    return dict(score=score,status='RATABLE' if ratable else 'NOT_RATABLE',component_scores=components,
        confidence=confidence,data_coverage=covered,evidence=details,warnings=warnings,model_version=VERSION,data_version=data_version,
        threshold_overrides=thresholds or {},company_limit=company_limit,sector_limit=sector_limit,sector_model=sector,decision=decision,portfolio_action=action,portfolio_weight=weight,sector_weight=sector_weight,
        valuation=valuation,margin_of_safety=mos,thesis_status=thesis,flags=flags,guidance=value('guidance_growth','percent'),
        target_weight_min=weight if action=='ADD_SMALL' else None,target_weight_max=min(company_limit,weight+min(1,sector_limit-sector_weight)) if action=='ADD_SMALL' else None,
        evaluated_at=now.isoformat(),previous_score=(previous or {}).get('score'))
