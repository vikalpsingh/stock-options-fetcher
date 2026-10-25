"""Versioned, configurable research thresholds, not forecasts or target prices."""
from copy import deepcopy

# component, metric, points, unit, bad threshold, good threshold.
BASE = [
 ('Growth','sales_cagr_3y',6,'percent',0,20),('Growth','pat_cagr_3y',7,'percent',0,20),
 ('Growth','quarterly_revenue_growth',5,'percent',0,20),('Growth','guidance_growth',6,'percent',0,20),('Growth','order_book_revenue',6,'ratio',0,3),
 ('Quality','roce',7,'percent',5,20),('Quality','opm',6,'percent',5,25),('Quality','cfo_pat',7,'ratio',0,1),
 ('Strength','debt_equity',6,'ratio',2,0),('Strength','interest_coverage',3,'ratio',1,5),('Strength','current_ratio',2,'ratio',0.5,2),('Strength','promoter_pledge',4,'percent',25,0),
 ('Valuation','pe_history_ratio',5,'ratio',2,0.7),('Valuation','peg',6,'ratio',3,0.7),('Valuation','ev_ebitda',4,'ratio',30,8),('Valuation','sector_valuation_ratio',5,'ratio',2,0.7),
 ('Governance','governance_quality',10,'score_100',0,100),('Entry','entry_quality',5,'score_100',0,100)]
# Pledge is scored once in Strength; governance_quality must exclude pledge.
REPLACEMENTS = {
 'GENERAL':{},'INDUSTRIAL':{},
 'EPC':{'opm':('opm',3,15)},
 'TECHNOLOGY':{'order_book_revenue':('deal_growth',0,20),'opm':('ebit_margin',5,25),'debt_equity':('client_concentration',60,10)},
 'PHARMA':{'order_book_revenue':('pipeline_quality',0,100),'opm':('opm',5,25)},
 'CONSUMER':{'order_book_revenue':('volume_growth',0,12)},
 'BANK':{'sales_cagr_3y':('loan_growth',0,20),'roce':('roa',0,2),'opm':('nim',1,5),'cfo_pat':('roe',0,18),
         'debt_equity':('gnpa',10,0),'interest_coverage':('capital_adequacy',9,18),'current_ratio':('liquidity_coverage',70,130),
         'peg':('pb',4,0.8),'ev_ebitda':('nnpa',5,0),'order_book_revenue':('deposit_growth',0,20)},
 'FINANCIAL_NBFC':{'sales_cagr_3y':('aum_growth',0,20),'roce':('roa',0,3),'opm':('nim',1,8),'cfo_pat':('roe',0,18),
         'debt_equity':('gnpa',10,0),'interest_coverage':('capital_adequacy',12,22),'current_ratio':('liquidity_coverage',70,130),
         'peg':('pb',4,0.8),'ev_ebitda':('credit_cost',4,0),'order_book_revenue':('funding_quality',0,100)},
 'REAL_ESTATE':{'sales_cagr_3y':('presales_growth',0,25),'pat_cagr_3y':('collections_growth',0,25),
         'order_book_revenue':('project_pipeline_revenue',0,4),'peg':('price_nav',2,0.6)},
 'NEW_AGE':{'pat_cagr_3y':('contribution_margin',-20,20),'roce':('unit_economics',0,100),'opm':('gross_margin',10,60),
         'cfo_pat':('cash_runway_months',3,36),'debt_equity':('dilution_pct',30,0),'interest_coverage':('profitability_path',0,100),
         'current_ratio':('current_ratio',0.5,2),'pe_history_ratio':('sales_history_ratio',2,0.7),
         'peg':('sector_valuation_ratio',2,0.7),'ev_ebitda':('burn_multiple',5,0.5),'order_book_revenue':('retention_pct',50,100)}
}
RATIOS={'pb','price_nav','sales_history_ratio','sector_valuation_ratio','burn_multiple','project_pipeline_revenue'}
SCORES={'pipeline_quality','funding_quality','unit_economics','profitability_path'}

def model(name, overrides=None):
    if name not in REPLACEMENTS:raise ValueError('Explicit supported sector model required.')
    rows=[]
    for component,metric,points,unit,bad,good in deepcopy(BASE):
        if metric in REPLACEMENTS[name]:
            metric,bad,good=REPLACEMENTS[name][metric]
            unit='ratio' if metric in RATIOS else 'score_100' if metric in SCORES else 'months' if metric=='cash_runway_months' else 'percent'
        if overrides and metric in overrides:
            bad,good=overrides[metric]
            import math
            if not all(math.isfinite(float(x)) for x in (bad,good)) or bad==good:raise ValueError('Invalid thresholds')
        rows.append((component,metric,points,unit,bad,good))
    # A metric must not be counted twice; reallocate duplicate weight in its component.
    seen=set();result=[]
    for row in rows:
        if row[1] in seen:
            row=(row[0],'valuation_support',row[2],'score_100',0,100)
        seen.add(row[1]);result.append(row)
    return result
