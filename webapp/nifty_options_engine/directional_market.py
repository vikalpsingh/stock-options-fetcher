"""Cached, account-session-scoped Kite history for NIFTY 2.0 only."""
from datetime import timedelta
import hashlib
import json
import logging
import threading
import time

from app_time import is_quote_fresh
from .directional_trend import (settings, timestamp, completed_candles, daily_indicators,
                                intraday_status, unavailable, DirectionalDataError)

logger = logging.getLogger(__name__)
_HISTORY_LOCK = threading.Lock()
_NEXT_REQUEST = 0.0


def historical(kite, token, start, end, interval):
    """Serialise this feature's history reads below Kite's historical request limit."""
    global _NEXT_REQUEST
    for attempt in range(3):
        try:
            with _HISTORY_LOCK:
                time.sleep(max(0, _NEXT_REQUEST-time.monotonic()))
                try:
                    return kite.historical_data(token, start, end, interval=interval)
                finally:
                    _NEXT_REQUEST = time.monotonic()+.36
        except Exception as exc:
            if getattr(exc, 'code', None) != 429 and getattr(exc, 'status_code', None) != 429:
                raise
            if attempt == 2:
                raise
            time.sleep(.5 * 2**attempt)


def load_directional_context(kite, account, now, instruments, spot_quote, config, cache=None, mmi=None, market_session=None):
    cfg, now = settings(config), timestamp(now)
    if not cfg['enabled']:
        result = unavailable(now, 'DTV disabled in NIFTY 2.0 configuration.')
        result.update(ce_status='ALLOW', pe_status='ALLOW', market_regime='DISABLED')
        return result
    # Only a digest enters cache keys. Failed/expired sessions cannot reuse another session's data.
    session = hashlib.sha256((str(account)+'|'+str(getattr(kite,'access_token',''))).encode()).hexdigest()
    cache = cache or (lambda key, fetch, ttl: fetch())
    prefix = 'nifty2:dtv:'+session+':'
    config_key = hashlib.sha256(json.dumps([cfg, {k:v for k,v in (market_session or {}).items() if k != 'asof'}],sort_keys=True).encode()).hexdigest()[:16]
    day_end = now.date() if (now.hour,now.minute) >= (15,35) else now.date()-timedelta(days=1)

    def compute():
        daily = None
        stage = 'instrument discovery'
        try:
            token = spot_quote.get('instrument_token')
            if not token:
                nse = cache(prefix+'nse:'+str(now.date()), lambda:kite.instruments('NSE'), 86400)
                token = next(row['instrument_token'] for row in nse if row.get('tradingsymbol') == 'NIFTY 50' and row.get('exchange')=='NSE')
            def load_daily():
                # 600 calendar days includes six months of history after 100 daily warm-up candles.
                raw = historical(kite,token,now-timedelta(days=600),now,'day')
                candles = completed_candles(raw,now,'day')
                if market_session:
                    cutoff = market_session.get('last_trading_date')
                    candles = [row for row in candles if cutoff and row['date'].date().isoformat() <= cutoff]
                return dict(candles=candles,history=daily_indicators(candles,cfg))
            stage = 'daily history / indicators'
            daily = cache(prefix+'daily:'+str(day_end)+':'+config_key,load_daily,cfg['daily_cache_seconds'])
            candles, history = daily['candles'], daily['history']
            last = history[-1]
            if (now.date()-candles[-1]['date'].date()).days > cfg['max_daily_age_days']:
                raise DirectionalDataError('Daily indicator candles are stale.')
            intraday = dict(continuation='Outside exchange session; confirmed daily history only',gap_pct=None,vwap=None)
            future_symbol = None
            spot = []
            if (market_session['regular_session_open'] if market_session else now.weekday()<5 and (9,15) <= (now.hour,now.minute) < (16,0)):
                stage = 'current spot timestamp'
                # Index payloads without a quote timestamp use the timestamped
                # completed-candle continuity check below, never receipt time.
                # This applies only to DTV history, not option execution quotes.
                if spot_quote.get('timestamp') and not is_quote_fresh(spot_quote,120,now):
                    raise DirectionalDataError('Current NIFTY spot quote is stale.')
                stage = 'completed five-minute spot candles'
                spot = completed_candles(historical(kite,token,now-timedelta(days=7),now,'5minute'),now,'5minute')
                previous = [row for row in candles if row['date'].date()<now.date()]
                if not previous:
                    raise DirectionalDataError('Previous daily close unavailable.')
                prior_intraday = [row for row in spot if row['date'].date()<now.date()]
                if prior_intraday and prior_intraday[-1]['date'].date()>previous[-1]['date'].date():
                    raise DirectionalDataError('Daily history does not include the previous observed session.')
                futures = []
                # Refresh choice each intraday TTL, with a roll buffer around expiry.
                contracts = sorted((row for row in instruments if row.get('name')=='NIFTY'
                    and row.get('instrument_type')=='FUT'
                    and str(row.get('expiry'))[:10]>(now.date()+timedelta(days=cfg['futures_roll_days'])).isoformat()),
                    key=lambda row:str(row['expiry']))[:3]
                try:
                    future_quotes = kite.quote(['NFO:'+row['tradingsymbol'] for row in contracts]) if contracts else {}
                    chosen = next((row for row in contracts if float((future_quotes.get('NFO:'+row['tradingsymbol']) or {}).get('volume') or 0)>0
                        and is_quote_fresh(future_quotes.get('NFO:'+row['tradingsymbol']) or {},120,now)),None)
                    if chosen:
                        future_symbol = chosen['tradingsymbol']
                        start = now.replace(hour=9,minute=15,second=0,microsecond=0)
                        futures = completed_candles(historical(kite,chosen['instrument_token'],start,now,'5minute'),now,'5minute')
                except Exception:
                    # A spot index has no usable volume proxy. Missing futures never creates VWAP.
                    future_symbol, futures = None, []
                stage = 'opening range / intraday continuity'
                intraday = intraday_status(spot,futures,previous[-1]['close'],last['atr_pct'],now,cfg)
            result = {**last, 'history':history, 'intraday':intraday,'future_symbol':future_symbol,
                      'data_asof':candles[-1]['date'].isoformat(), 'calculated_at':now.isoformat(),
                      'data_source':'Kite historical', 'valid_until':(now+timedelta(seconds=cfg['intraday_cache_seconds'])).isoformat()}
            result['reasons'] = dict(last['reasons'])
            for side in ('CE','PE'):
                if intraday.get(side.lower()+'_status')=='BLOCK':
                    result[side.lower()+'_status']='BLOCK'
                    result['reasons'][side]='Opening gap protection. '+intraday['continuation']
            if market_session:
                from .market_session import validate_market_data_freshness
                result['market_session'] = market_session
                result['intraday_validation'] = ('MARKET CLOSED' if not market_session['regular_session_open'] else 'AWAITING OPENING RANGE' if not intraday.get('asof') else 'CONFIRMED')
                result['freshness'] = validate_market_data_freshness(market_session, spot_quote, candles, spot)
                result['daily_regime'] = last['market_regime']
                base_ema = last['ema20']-last['ema_slope']
                result['ema_slope_pct'] = 100*last['ema_slope']/base_ema if base_ema else None
                result['ema_slope_sessions'] = 3
                if not market_session['regular_session_open']:
                    result['intraday'] = dict(continuation='MARKET CLOSED — intraday entry validation not applicable', gap_pct=None, vwap=None)
                    for side in ('CE','PE'):
                        result[side.lower()+'_status'] = 'BLOCK'
                        result['reasons'][side] = 'Market closed: '+market_session['reason']+'. Daily trend: '+last['market_regime']
            return result
        except Exception as exc:
            # SDK messages can contain tokens or URLs. Only local validation messages are exposed.
            detail = str(exc) if isinstance(exc, DirectionalDataError) else type(exc).__name__
            reason = stage + ': ' + detail + ' Refresh market data; check Kite historical access if this persists.'
            result = unavailable(now,reason)
            # An intraday failure must not erase independently verified daily history.
            # Both entry directions remain blocked until current-session evidence recovers.
            if daily and daily.get('history') and stage not in {'instrument discovery','daily history / indicators'}:
                last = daily['history'][-1]
                result.update({key:value for key,value in last.items()
                               if key not in {'ce_status','pe_status','reasons','market_regime'}})
                result.update(history=daily['history'], data_asof=daily['candles'][-1]['date'].isoformat(),
                              data_source='Kite historical', market_regime=last['market_regime']+' / INTRADAY UNVERIFIED')
            if market_session:
                result['market_session'] = market_session
                result['freshness'] = dict(status='MISSING' if isinstance(exc, DirectionalDataError) else 'API_ERROR')
                result['intraday_validation'] = 'MARKET CLOSED' if not market_session['regular_session_open'] else 'UNAVAILABLE'
                if daily and daily.get('history'):
                    result['daily_regime'] = daily['history'][-1]['market_regime']
            return result

    # Cache failure states briefly as well, avoiding repeated API bursts on one preview.
    result = cache(prefix+'snapshot:'+config_key+':'+str(now.date())+':'+str(day_end), compute, min(cfg['intraday_cache_seconds'], cfg['failure_cache_seconds']))
    result['mmi_recommendation'] = mmi or 'UNAVAILABLE'
    decisions = {side:('NO NEW '+side+' SELL' if result[side.lower()+'_status']=='BLOCK' else 'Existing checks required') for side in ('CE','PE')}
    result['final_decision'] = decisions
    # One diagnostic per cached calculation + MMI observation, not per optimizer candidate.
    def log_snapshot():
        payload = {key:result.get(key) for key in ('data_source','data_asof','er5','er10','adx14','plus_di','minus_di','return_5d','market_regime','mmi_recommendation','final_decision')}
        payload.update(timestamp=result['calculated_at'],gap_pct=result['intraday'].get('gap_pct'),
                       dtv_ce_status=result['ce_status'],dtv_pe_status=result['pe_status'],veto_reason=result['reasons'])
        logger.info('NIFTY2_DTV %s',json.dumps(payload,sort_keys=True))
        return True
    cache(prefix+'log:'+result['calculated_at']+':'+str(mmi),log_snapshot,cfg['daily_cache_seconds'])
    return result


def request_refresh_cache():
    """Bypass shared cache for one explicit refresh, deduplicating page builds."""
    from copy import deepcopy
    values = {}
    def cached(key, fetch, ttl):
        if key not in values:
            values[key] = deepcopy(fetch())
        return deepcopy(values[key])
    return cached
