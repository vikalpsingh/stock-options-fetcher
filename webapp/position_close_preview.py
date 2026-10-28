"""Read-only presentation of scheduler candidates; no broker submission dependency."""
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from position_close_safety import key, validate_close_submission


def preview_rows(positions, pending, candidates, owned, stop_sell, notes):
    orders = {key(order): order for order in candidates}
    rows = []
    for position in positions:
        symbol = str(position.get('tradingsymbol') or '')
        qty = int(position.get('quantity') or 0)
        if not qty or position.get('exchange') != 'NFO' or not symbol.endswith(('CE', 'PE')):
            continue
        order = orders.get(key(position))
        side = 'BUY' if qty < 0 else 'SELL'
        status = 'PROPOSED — NOT SENT' if order else 'SKIPPED'
        reason = str(notes.get(symbol) or 'No candidate: existing order, saved filters or risk controls.') if not order else str(order.get('risk_note') or order.get('price_basis') or 'Configured close target')
        if order:
            try:
                if symbol in owned:
                    raise ValueError('Protected pair: use EXECUTION Close Pair.')
                if stop_sell and side == 'SELL':
                    raise ValueError('STOP OPTION SELL is enabled.')
                validate_close_submission(order, positions, pending)
            except ValueError as exc:
                status, reason = 'BLOCKED', str(exc)
        rows.append(dict(symbol=symbol, product=position.get('product'), position_qty=qty,
                         average=position.get('average_price'), cmp=(order or {}).get('ltp') or position.get('last_price'),
                         side=(order or {}).get('transaction_type', side), quantity=(order or {}).get('quantity'),
                         price=(order or {}).get('price'), status=status, reason=reason))
    return rows


def render_preview(rows):
    if rows is None:
        return ''
    columns = [('symbol','Contract'),('product','Product'),('position_qty','Signed position'),
               ('average','Average'),('cmp','CMP'),('side','Close side'),('quantity','Order qty'),
               ('price','LIMIT'),('status','Test result'),('reason','Reason')]
    stamp = datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%d %b %Y %H:%M:%S IST')
    body = ''.join('<tr>' + ''.join('<td>' + escape(str(row.get(field) if row.get(field) is not None else '—')) + '</td>' for field,_ in columns) + '</tr>' for row in rows)
    return ('<div class="close-job-test-results"><p><strong>TEST RUN — NO ORDERS SENT</strong> · '+stamp+
            '. Uses saved settings and current data; schedule/session eligibility is not an execution approval.</p>'+
            ('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+label+'</th>' for _,label in columns)+'</tr></thead><tbody>'+body+'</tbody></table></div>' if rows else '<p>No active option positions.</p>')+'</div>')
