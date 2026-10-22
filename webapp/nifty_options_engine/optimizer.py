"""Read-only candidate comparison; all payoff/risk checks belong to build_ticket."""
import math
from .ticket import build_ticket, depth_limit, quote_values, is_hundred_strike
from app_time import is_quote_fresh


def generate_nifty_short_strike_candidates(base_strike, option_type, step=100):
    if option_type not in {"PE", "CE"} or step != 100:
        raise ValueError("NIFTY candidates require PE/CE and a 100-point grid")
    base = (math.floor(float(base_strike)/step) if option_type == "PE" else math.ceil(float(base_strike)/step))*step
    direction = -1 if option_type == "PE" else 1
    return [dict(label=label, strike=base+offset*direction*step) for label,offset in
            zip(("CLOSER_2","CLOSER_1","BASE","FARTHER_1","FARTHER_2"),(-2,-1,0,1,2))]


def candidate_contracts(selection, instruments, width=300):
    result = {}
    for side in ("PE", "CE"):
        master = [r for r in instruments if r.get("name")=="NIFTY" and r.get("instrument_type")==side
                  and str(r.get("expiry"))[:10]==selection.get("expiry") and is_hundred_strike(r)]
        base = next((r for r in master if r["tradingsymbol"]==(selection.get("base_"+side.lower()) or selection.get("short_"+side.lower()))), None)
        result[side] = []
        if not base:
            continue
        for row in generate_nifty_short_strike_candidates(base["strike"],side):
            short = next((r for r in master if float(r["strike"])==row["strike"]),None)
            target = row["strike"] + (-width if side=="PE" else width)
            hedges = [r for r in master if float(r["strike"])<=target] if side=="PE" else [r for r in master if float(r["strike"])>=target]
            hedge = min(hedges,key=lambda r:abs(float(r["strike"])-target)) if hedges else None
            result[side].append(dict(row, short=short, hedge=hedge))
    return result


def candidate_quote_keys(selection, instruments, width):
    return sorted({"NFO:"+r[leg]["tradingsymbol"] for rows in candidate_contracts(selection,instruments,width).values()
                   for r in rows for leg in ("short","hedge") if r[leg]})


def rank_nifty_spread_candidates(candidates, market_state=None, config=None):
    # Missing regime/Greeks/event/expected-move observations earn no invented points.
    return sorted((r for r in candidates if r["eligible"]),
                  key=lambda r:(r["score"],r["ticket"]["net_max_profit"]), reverse=True)


def optimize_spreads(selection, context, config):
    tables = candidate_contracts(selection,context["instruments"],config["default_hedge_width_points"])
    spot = float(context.get("spot") or 0)
    for side, rows in tables.items():
        for row in rows:
            row.update(eligible=False, score=0, reasons=[], ticket=None, otm=None,
                       confidence="Limited: Greeks, regime, expected move and event scoring unavailable")
            short, hedge = row["short"], row["hedge"]
            if not short or not hedge:
                row["reasons"]=["Listed short or farther-OTM hedge unavailable"]
                continue
            row["width"] = abs(float(short["strike"])-float(hedge["strike"]))
            row["otm"] = ((spot-row["strike"]) if side=="PE" else (row["strike"]-spot))/spot*100 if spot else None
            proposed = dict(selection,include_pe=side=="PE",include_ce=side=="CE")
            proposed["short_"+side.lower()] = short["tradingsymbol"]
            proposed["hedge_"+side.lower()] = hedge["tradingsymbol"]
            ticket = build_ticket(proposed,context,config,for_execution=False)
            row["ticket"] = ticket
            row["reasons"] = [c["name"]+": "+c["reason"] for c in ticket["checks"] if c["status"]=="BLOCK"]
            if row["otm"] is None or row["otm"]<=0:
                row["reasons"].append("Short must remain OTM relative to current spot")
            quality = True
            spread_penalty = 0.0
            for instrument, action in ((short,"SELL"),(hedge,"BUY")):
                quote = context["quotes"].get("NFO:"+instrument["tradingsymbol"],{})
                qty = int(instrument["lot_size"])*int(selection["lots"])
                values = quote_values(quote)
                bid,ask = values["bid"], values["ask"]
                if not bid or not ask or ask<bid:
                    row["reasons"].append("PREVIEW_ONLY: executable bid/ask unavailable")
                    quality=False
                elif (ask-bid)/bid*100 > config.get("max_bid_ask_spread_pct",8):
                    row["reasons"].append("Spread too wide for automatic selection")
                    quality=False
                if bid and ask and ask >= bid:
                    spread_penalty += min(12.5, (ask-bid)/bid*100 / max(0.01, config.get("max_bid_ask_spread_pct",8)) * 12.5)
                if depth_limit(quote,action,qty)["shortfall"]>0:
                    row["reasons"].append("Insufficient displayed depth for selected quantity")
                    quality=False
                if not is_quote_fresh(quote,120,context["now"]):
                    row["reasons"].append("Fresh exchange quote required for automatic selection")
                    quality=False
            loss = ticket["max_loss"]
            row["reward_risk"] = ticket["net_max_profit"]/loss if loss and loss>0 else None
            # 30 optional-information points are not fabricated; available components total 70.
            efficiency = min(25,max(0,(row["reward_risk"] or 0)*25))
            safety = min(20,max(0,(row["otm"] or 0)/2*20))
            row["score"] = round((max(0,25-spread_penalty) if quality else 0)+efficiency+safety,2)
            row["eligible"] = not row["reasons"]
    ranked = {side:rank_nifty_spread_candidates(rows) for side,rows in tables.items()}
    chosen = {side:(rows[0] if rows else None) for side,rows in ranked.items()}
    combinations = []
    if selection.get("include_pe") and selection.get("include_ce"):
        for pe in ranked["PE"]:
            for ce in ranked["CE"]:
                if pe["strike"]>=ce["strike"]:
                    continue
                proposed = dict(selection)
                for side,row in (("pe",pe),("ce",ce)):
                    proposed["short_"+side]=row["short"]["tradingsymbol"]
                    proposed["hedge_"+side]=row["hedge"]["tradingsymbol"]
                ticket=build_ticket(proposed,context,config,for_execution=False)
                if ticket["eligible"]:
                    combinations.append((pe["score"]+ce["score"],ticket["net_max_profit"],pe,ce))
        best=max(combinations,key=lambda c:c[:2]) if combinations else None
        chosen={"PE":best[2] if best else None,"CE":best[3] if best else None}
    for side, rows in tables.items():
        for row in rows:
            row['recommended'] = row is chosen[side]
    return dict(tables=tables, chosen=chosen, combination_count=len(combinations))


def maximum_credit_preview(rows):
    """Fallback selection is not approval; require real quoted credit and valid legs."""
    candidates = []
    for row in rows:
        ticket = row.get('ticket')
        if not ticket or not row.get('short') or not row.get('hedge'):
            continue
        if row.get('otm') is None or row['otm'] <= 0:
            continue
        legs = ticket.get('legs') or []
        if len(legs) != 2 or not all(leg.get('bid') and leg.get('ask') and
                0 < leg['bid'] <= leg['ask'] for leg in legs):
            continue
        credit = ticket.get('net_credit')
        if credit is not None and math.isfinite(credit) and credit > 0:
            candidates.append(row)
    eligible = [row for row in candidates if row['eligible']]
    return max(eligible or candidates, key=lambda row:row['ticket']['net_credit'], default=None)
