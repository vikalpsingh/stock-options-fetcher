"""Shared server-side exit consent; no broker access or financial side effects."""
from datetime import datetime, timezone
import math
from trade_protected_execution import basket_remaining


def exit_stage(record):
    return 'HEDGES' if all(basket_remaining(record,leg)==0 for leg in record['legs'] if leg['payload']['transaction_type']=='SELL') else 'SHORTS'


def save_exit_review(repo, record, prices, target=50, now=None):
    target=float(target)
    if not math.isfinite(target) or not 0<=target<=100:raise ValueError('Profit target must be 0–100%.')
    record['close_review']=dict(at=(now or datetime.now(timezone.utc)).isoformat(),stage=exit_stage(record),
        prices=prices,target_percent=target,remaining={leg['payload']['tradingsymbol']:basket_remaining(record,leg) for leg in record['legs']})
    return repo.save(record)


def validate_exit_review(record, prices, now=None):
    review=record.get('close_review') or {}
    try:age=((now or datetime.now(timezone.utc))-datetime.fromisoformat(review['at'])).total_seconds()
    except (KeyError,ValueError,TypeError):raise PermissionError('Review Exit before confirming.')
    remaining={leg['payload']['tradingsymbol']:basket_remaining(record,leg) for leg in record['legs']}
    if not 0<=age<=120 or review.get('stage')!=exit_stage(record) or review.get('remaining')!=remaining:
        raise PermissionError('Exit review expired or quantities changed. Review Exit again.')
    for leg in record['legs']:
        symbol=leg['payload']['tradingsymbol']
        if symbol not in prices:continue
        old=review.get('prices',{}).get(symbol);new=prices[symbol]
        if old is None or not math.isfinite(new) or new<=0 or (new>old if leg['payload']['transaction_type']=='SELL' else new<old):
            raise PermissionError('Exit price worsened. Review Exit again.')


def render_exit_review(record, action, account_field, account):
    from html import escape as e
    review=record.get('close_review') or {}
    if not review:return ''
    rows=''.join('<tr><td>'+e(leg['payload']['tradingsymbol'])+'</td><td>'+('BUY short' if leg['payload']['transaction_type']=='SELL' else 'SELL hedge')+'</td><td>'+str(basket_remaining(record,leg))+'</td><td>'+e(str(review.get('prices',{}).get(leg['payload']['tradingsymbol'],'Next stage')))+'</td></tr>' for leg in record['legs'])
    dialog_id='exit-review-'+str(record.get('id','pair'))
    content='<h3>Review Exit</h3><p>Target '+e(str(review.get('target_percent',50)))+'% is advisory. A loss-making risk exit is permitted. Review expires after 120 seconds.</p><table><thead><tr><th>Contract</th><th>Close action</th><th>Remaining qty</th><th>LIMIT</th></tr></thead><tbody>'+rows+'</tbody></table><p>Only the current stage is authorised. Remaining hedges require a fresh review after short fills are confirmed.</p>'
    return '<button type="button" onclick="document.getElementById(\''+e(dialog_id)+'\').showModal()">Review Exit prices</button><dialog id="'+e(dialog_id)+'" style="max-width:90vw;border:1px solid #99c9c5;border-radius:12px;padding:24px">'+content+'<button type="button" onclick="this.closest(\'dialog\').close()">Back to explicit confirmation</button></dialog>'



def executable_exit_limit(quote, side, quantity, tick_size, now):
    """Fresh full-quantity depth; adverse-direction rounding to the master tick."""
    from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
    from app_time import is_quote_fresh
    from nifty_options_engine.ticket import depth_limit
    try:
        tick = Decimal(str(tick_size))
        if not tick.is_finite() or tick <= 0:
            raise ValueError()
        depth = depth_limit(quote, side, quantity)
        if not is_quote_fresh(quote, 120, now) or depth['shortfall'] or not depth['limit']:
            raise ValueError()
        price = Decimal(str(depth['limit']))
        price = (price/tick).to_integral_value(rounding=ROUND_CEILING if side=='BUY' else ROUND_FLOOR)*tick
        if not price.is_finite() or price <= 0:
            raise ValueError()
        return float(price)
    except (ValueError, TypeError, ArithmeticError):
        raise PermissionError('Fresh executable depth and instrument tick size are required for exit.')
