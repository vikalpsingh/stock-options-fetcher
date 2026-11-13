"""NIFTY 2.0 directional indicators and fail-closed entry veto."""
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

class DirectionalDataError(ValueError):
    """Safe local validation message; never contains raw broker responses."""


IST = ZoneInfo('Asia/Kolkata')
DTV_CONFIG = {
    'enabled': True, 'adx_period': 14, 'adx_trend_threshold': 25,
    'adx_developing_threshold': 20, 'er_fast_period': 5, 'er_slow_period': 10,
    'er_warning_threshold': .35, 'er_veto_threshold': .70, 'return_5d_threshold': .02,
    'ema_period': 20, 'atr_period': 14, 'breakout_lookback': 5,
    'gap_threshold_pct': .75, 'opening_range_minutes': 15,
    'daily_cache_seconds': 1800, 'intraday_cache_seconds': 30,
    'failure_cache_seconds': 15, 'max_daily_age_days': 7, 'futures_roll_days': 1,
}


def settings(config):
    overrides = config.get('directional_trend_veto') or {}
    result = {**DTV_CONFIG, **{k: v for k, v in overrides.items() if k in DTV_CONFIG}}
    for key, default in DTV_CONFIG.items():
        value = result[key]
        if isinstance(default, bool):
            if type(value) is not bool:
                raise DirectionalDataError('DTV enabled must be true or false.')
        elif not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value <= 0:
            raise DirectionalDataError('Invalid DTV setting: ' + key)
        elif isinstance(default, int) and (int(value) != value or value > 2000):
            raise DirectionalDataError('Invalid DTV integer setting: ' + key)
        elif isinstance(default, int):
            result[key] = int(value)
    if not 0 < result['er_warning_threshold'] < result['er_veto_threshold'] <= 1:
        raise DirectionalDataError('DTV ER thresholds must be ordered within (0, 1].')
    if not 0 < result['adx_developing_threshold'] < result['adx_trend_threshold'] <= 100:
        raise DirectionalDataError('DTV ADX thresholds must be ordered within (0, 100].')
    if result['opening_range_minutes'] % 5 or result['opening_range_minutes'] > 60:
        raise DirectionalDataError('DTV opening range must be a multiple of five minutes, at most 60.')
    return result


def timestamp(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def completed_candles(raw, now, interval):
    now = timestamp(now)
    rows = {}
    for item in raw:
        at = timestamp(item['date'])
        end = at.replace(hour=15, minute=35, second=0, microsecond=0) if interval == 'day' else at + timedelta(minutes=5)
        if end > now or at > now:
            continue
        if interval != 'day' and not (9, 15) <= (at.hour, at.minute) < (15, 30):
            continue
        row = {key: float(item[key]) for key in ('open', 'high', 'low', 'close')}
        if not all(isfinite(v) and v > 0 for v in row.values()) or not row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']:
            raise DirectionalDataError('Invalid OHLC candles.')
        row.update(date=at, volume=item.get('volume'))
        # Reject ambiguous duplicated timestamps instead of silently revising history.
        key = at.date() if interval == 'day' else at
        if key in rows and rows[key] != row:
            raise DirectionalDataError('Conflicting candle timestamps.')
        rows[key] = row
    return [rows[key] for key in sorted(rows)]


def efficiency(closes, index, period):
    if index < period:
        return None
    path = sum(abs(closes[j] - closes[j-1]) for j in range(index-period+1, index+1))
    return abs(closes[index]-closes[index-period])/path if path else 0.0


def wilder(values, period):
    output = [None] * len(values)
    if len(values) >= period:
        output[period-1] = sum(values[:period])/period
        for i in range(period, len(values)):
            output[i] = (output[i-1]*(period-1)+values[i])/period
    return output


def daily_status(point, cfg):
    early_bull = point['er5'] >= cfg['er_veto_threshold'] and point['return_5d'] >= cfg['return_5d_threshold'] and point['close'] > point['previous_high']
    early_bear = point['er5'] >= cfg['er_veto_threshold'] and point['return_5d'] <= -cfg['return_5d_threshold'] and point['close'] < point['previous_low']
    strong = point['adx14'] >= cfg['adx_trend_threshold']
    bull = strong and point['plus_di'] > point['minus_di']
    bear = strong and point['minus_di'] > point['plus_di']
    developing = cfg['adx_developing_threshold'] <= point['adx14'] < cfg['adx_trend_threshold'] and point['adx14'] > point['previous_adx']
    ce, pe = 'ALLOW', 'ALLOW'
    reasons = {'CE': 'Daily trend permits existing strategy checks.', 'PE': 'Daily trend permits existing strategy checks.'}
    regime = 'SIDEWAYS'
    if early_bull or bull:
        ce, regime = 'BLOCK', 'STRONG BULL'
        reasons['CE'] = 'Bullish directional momentum prohibits new CE SELL exposure.'
        if early_bull and not bull:
            pe = 'CAUTION'
    if early_bear or bear:
        pe, regime = 'BLOCK', 'STRONG BEAR'
        reasons['PE'] = 'Bearish directional momentum prohibits new PE SELL exposure.'
        if early_bear and not bear:
            ce = 'CAUTION'
    if developing and not (early_bull or early_bear or bull or bear):
        if point['plus_di'] > point['minus_di']:
            ce, regime = 'CAUTION', 'BULL DEVELOPING'
        elif point['minus_di'] > point['plus_di']:
            pe, regime = 'CAUTION', 'BEAR DEVELOPING'
    for side, status in [('CE', ce), ('PE', pe)]:
        if status == 'CAUTION':
            reasons[side] = 'Developing directional risk. Require full executable depth, configured spread limit and bounded payoff.'
    if ce == pe == 'BLOCK':
        regime = 'MIXED / TRANSITION'
    return dict(ce_status=ce, pe_status=pe, market_regime=regime, reasons=reasons)


def daily_indicators(candles, cfg):
    closes = [row['close'] for row in candles]
    adx_period, atr_period, ema_period = cfg['adx_period'], cfg['atr_period'], cfg['ema_period']
    if len(candles) < max(100, adx_period*2+2, ema_period+3, cfg['er_slow_period']+1, cfg['breakout_lookback']+1):
        raise DirectionalDataError('At least 100 completed daily candles and full indicator warm-up required.')
    tr, up_dm, down_dm = [], [], []
    for before, current in zip(candles, candles[1:]):
        tr.append(max(current['high']-current['low'], abs(current['high']-before['close']), abs(current['low']-before['close'])))
        up, down = current['high']-before['high'], before['low']-current['low']
        up_dm.append(up if up > down and up > 0 else 0)
        down_dm.append(down if down > up and down > 0 else 0)
    smooth_tr, smooth_up, smooth_down = [wilder(values, adx_period) for values in (tr, up_dm, down_dm)]
    atr = wilder(tr, atr_period)
    plus, minus, dx = {}, {}, []
    for i in range(adx_period-1, len(tr)):
        plus[i+1] = 100*smooth_up[i]/smooth_tr[i] if smooth_tr[i] else 0
        minus[i+1] = 100*smooth_down[i]/smooth_tr[i] if smooth_tr[i] else 0
        total = plus[i+1]+minus[i+1]
        dx.append(100*abs(plus[i+1]-minus[i+1])/total if total else 0)
    adx_values = wilder(dx, adx_period)
    adx = {i+adx_period: value for i, value in enumerate(adx_values) if value is not None}
    ema = {ema_period-1: sum(closes[:ema_period])/ema_period}
    for i in range(ema_period, len(closes)):
        ema[i] = ema[i-1]+2/(ema_period+1)*(closes[i]-ema[i-1])
    history = []
    higher = lower = 0
    for i, candle in enumerate(candles):
        if i:
            higher = higher+1 if closes[i] > closes[i-1] else 0
            lower = lower+1 if closes[i] < closes[i-1] else 0
        warmup = max(99, adx_period*2, ema_period+2, cfg['er_fast_period'], cfg['er_slow_period'], cfg['breakout_lookback'], atr_period, 5)
        if i < warmup:
            continue
        reference = closes[i-cfg['breakout_lookback']:i]
        point = dict(date=candle['date'].date().isoformat(), close=closes[i],
                     er5=efficiency(closes,i,cfg['er_fast_period']), er10=efficiency(closes,i,cfg['er_slow_period']),
                     adx14=adx[i], previous_adx=adx[i-1], plus_di=plus[i], minus_di=minus[i],
                     atr14=atr[i-1], atr_pct=100*atr[i-1]/closes[i], ema20=ema[i], ema_slope=ema[i]-ema[i-3],
                     previous_high=max(reference), previous_low=min(reference), return_5d=closes[i]/closes[i-5]-1,
                     higher_closes=higher, lower_closes=lower)
        point.update(daily_status(point,cfg))
        history.append(point)
    return history


def intraday_status(spot, futures, previous_close, atr_pct, now, cfg):
    now = timestamp(now)
    today = [row for row in spot if row['date'].date() == now.date()]
    opening = now.replace(hour=9, minute=15, second=0, microsecond=0)
    result = dict(gap_pct=None, gap_atr=None, continuation='UNAVAILABLE', vwap=None, futures_close=None,
                  ce_status='ALLOW', pe_status='ALLOW', asof=None)
    expected = min(now.replace(hour=15,minute=30), now).replace(second=0,microsecond=0)
    expected -= timedelta(minutes=expected.minute % 5)
    if now.weekday() >= 5 or now < opening or now.hour >= 16:
        result['continuation'] = 'Outside exchange session; confirmed daily history only'
        return result
    if not today or today[0]['date'] != opening or today[-1]['date']+timedelta(minutes=5) < expected:
        raise DirectionalDataError('Completed current-session spot candles unavailable or stale.')
    if any(b['date']-a['date'] != timedelta(minutes=5) for a,b in zip(today,today[1:])):
        raise DirectionalDataError('Intraday spot candle gap; refresh required.')
    gap = 100*(today[0]['open']/previous_close-1)
    result.update(gap_pct=gap, gap_atr=abs(gap)/atr_pct if atr_pct else None,
                  asof=today[-1]['date'].isoformat(), continuation='No absolute gap veto')
    future_today = [row for row in futures if row['date'].date() == now.date()]
    volume, value, future_points = 0, 0, {}
    valid_volume = bool(future_today) and future_today[0]['date'] == opening and future_today[-1]['date'] == today[-1]['date']
    for index, row in enumerate(future_today):
        try:
            vol = float(row.get('volume'))
        except (ValueError, TypeError):
            valid_volume = False
            break
        if not isfinite(vol) or vol <= 0 or (index and row['date']-future_today[index-1]['date'] != timedelta(minutes=5)):
            valid_volume = False
            break
        volume += vol
        value += (row['high']+row['low']+row['close'])/3*vol
        future_points[row['date']] = (row['close'], value/volume)
    if valid_volume and volume:
        result.update(vwap=value/volume, futures_close=future_today[-1]['close'])
    if abs(gap) < cfg['gap_threshold_pct']:
        return result
    side = 'ce_status' if gap > 0 else 'pe_status'
    result[side] = 'BLOCK'
    end = opening+timedelta(minutes=cfg['opening_range_minutes'])
    opening_rows = [row for row in today if row['date'] < end]
    if now < end or len(opening_rows) < cfg['opening_range_minutes']//5:
        result['continuation'] = 'Opening gap veto; first opening range is incomplete'
        return result
    high, low = max(row['high'] for row in opening_rows), min(row['low'] for row in opening_rows)
    for index, row in enumerate(today):
        if row['date'] < end or not index:
            continue
        future = future_points.get(row['date']) if valid_volume else None
        direction = row['close'] > high and row['close'] > today[index-1]['close'] if gap > 0 else row['close'] < low and row['close'] < today[index-1]['close']
        confirmed = future and (future[0] > future[1] if gap > 0 else future[0] < future[1])
        if direction and confirmed:
            result['continuation'] = 'Gap continuation confirmed; veto retained for this session'
            return result
    result['continuation'] = 'Gap veto retained; continuation unconfirmed' + (' / futures VWAP unavailable' if not valid_volume else '')
    return result


def unavailable(now, reason):
    return dict(ce_status='BLOCK', pe_status='BLOCK', market_regime='UNAVAILABLE', history=[],
                data_asof=None, calculated_at=timestamp(now).isoformat(), valid_until=timestamp(now).isoformat(),
                reasons={'CE': reason, 'PE': reason}, intraday={}, data_source='Kite historical')


def entry_checks(selection, context, config):
    cfg = settings(config)
    if not cfg['enabled']:
        return []
    data = context.get('dtv') or unavailable(context['now'], 'Directional indicator data unavailable; refresh preview.')
    try:
        fresh = timestamp(data['valid_until']) >= timestamp(context['now']) >= timestamp(data['calculated_at'])
    except (KeyError, ValueError, TypeError):
        fresh = False
    checks = []
    for side in ('CE','PE'):
        if not selection.get('include_'+side.lower()):
            continue
        status = data.get(side.lower()+'_status', 'BLOCK') if fresh else 'BLOCK'
        if status not in {'ALLOW','CAUTION','BLOCK'}:
            status = 'BLOCK'
        reason = (data.get('reasons') or {}).get(side, 'Directional evidence unavailable.') if fresh else 'Directional evidence expired; refresh preview.'
        checks.append(dict(name='Directional Trend Veto '+side, status='PASS' if status=='ALLOW' else status, reason=reason))
    return checks
