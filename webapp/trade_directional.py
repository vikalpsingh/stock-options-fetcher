"""TRADE-only directional context; reuse NIFTY calculations, history transport and charting."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import logging
from html import escape
from nifty_options_engine.directional_market import historical, load_directional_context
from nifty_options_engine.directional_trend import (settings, timestamp, completed_candles,
    daily_indicators, intraday_status, unavailable, DirectionalDataError)

logger=logging.getLogger(__name__)


def sector_key(symbol):
    from sector_income import SECTOR_INCOME_UNIVERSE, SECTOR_INDEX_CONFIG
    matches=[key for key, symbols in SECTOR_INCOME_UNIVERSE.items() if symbol in symbols]
    if len(matches)!=1:return None
    key=SECTOR_INDEX_CONFIG.get(matches[0],{}).get('kite_symbol','')
    return key if key.startswith('NSE:') else None


def load_trade_trends(kite, account, symbol, now, *, cache, nse, nfo, config):
    now=timestamp(now);cfg=settings(config);symbol=str(symbol).upper()
    session=hashlib.sha256((str(account)+'|'+str(getattr(kite,'access_token',''))).encode()).hexdigest()
    prefix='trade:dtv:'+session+':'+hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()[:12]+':'
    master={row['tradingsymbol']:row for row in nse if row.get('exchange')=='NSE'}
    def load(key):
        instrument=master.get(key.removeprefix('NSE:'))
        if not instrument or not instrument.get('instrument_token'):
            return unavailable(now,'Verified underlying NSE instrument unavailable: '+key)
        def compute():
            daily=None
            try:
                token=instrument['instrument_token']
                day=now.date() if (now.hour,now.minute)>=(15,35) else now.date()-timedelta(days=1)
                def daily_data():
                    candles=completed_candles(historical(kite,token,now-timedelta(days=600),now,'day'),now,'day')
                    return candles,daily_indicators(candles,cfg)
                candles,history=cache(prefix+key+':daily:'+str(day),daily_data,cfg['daily_cache_seconds'])
                daily=history[-1]
                if (now.date()-candles[-1]['date'].date()).days>cfg['max_daily_age_days']:
                    raise DirectionalDataError('Completed daily history is stale.')
                intraday=dict(continuation='Outside session; completed daily history',gap_pct=None,vwap=None)
                if now.weekday()<5 and (9,15)<=(now.hour,now.minute)<(16,0):
                    bars=completed_candles(historical(kite,token,now-timedelta(days=7),now,'5minute'),now,'5minute')
                    previous=[row for row in candles if row['date'].date()<now.date()]
                    prior=[row for row in bars if row['date'].date()<now.date()]
                    if not previous or (prior and prior[-1]['date'].date()>previous[-1]['date'].date()):
                        raise DirectionalDataError('Previous completed session is missing from daily history.')
                    # Stock candles carry actual traded volume. Indices never use a fake VWAP.
                    volume_bars=bars if instrument.get('instrument_type')=='EQ' else []
                    intraday=intraday_status(bars,volume_bars,previous[-1]['close'],daily['atr_pct'],now,cfg)
                result={**daily,'history':history,'intraday':intraday,'data_asof':candles[-1]['date'].isoformat(),
                    'calculated_at':now.isoformat(),'valid_until':(now+timedelta(seconds=cfg['intraday_cache_seconds'])).isoformat(),
                    'data_source':'Kite '+key,'future_symbol':key}
                result['reasons']=dict(daily['reasons'])
                result['normalized_ema_slope_pct']=daily['ema_slope']/daily['ema20']*100 if daily['ema20'] else None
                for side in ('CE','PE'):
                    if intraday.get(side.lower()+'_status')=='BLOCK':
                        result[side.lower()+'_status']='BLOCK';result['reasons'][side]=intraday['continuation']
                return result
            except Exception as exc:
                reason=str(exc) if isinstance(exc,DirectionalDataError) else 'Historical data unavailable ('+type(exc).__name__+').'
                result=unavailable(now,reason)
                if daily:
                    result.update({k:v for k,v in daily.items() if k not in {'ce_status','pe_status','reasons','market_regime'}})
                    result.update(history=history,data_asof=candles[-1]['date'].isoformat())
                return result
        return cache(prefix+key+':snapshot',compute,min(cfg['intraday_cache_seconds'],cfg['failure_cache_seconds']))
    def market_data():
        quote=kite.quote(['NSE:NIFTY 50']).get('NSE:NIFTY 50') or {}
        return load_directional_context(kite,account,now,nfo,quote,config,cache)
    try:
        market=cache(prefix+'market',market_data,min(cfg['intraday_cache_seconds'],cfg['failure_cache_seconds']))
    except Exception:
        market=unavailable(now,'NIFTY market context unavailable.')
    key=sector_key(symbol) if symbol not in {'NIFTY','NIFTY 50'} else None
    stock=market if symbol in {'NIFTY','NIFTY 50'} else load('NSE:'+symbol)
    sector=load(key) if key else None
    return dict(symbol=symbol,stock=stock,sector=sector,sector_symbol=key,market=market,config=cfg)


def decision(context, side, option_type, now, *, reducing=False, verified_covered_call=False, covered_policy='BLOCK'):
    if side!='SELL' or option_type not in {'CE','PE'} or reducing:
        return dict(name='Directional trend risk',status='PASS',decision='ALLOW',reason='Directional entry veto does not apply to buys, non-option sales or verified position reductions.')
    stock=context.get('stock') or {};sector=context.get('sector');market=context.get('market') or {}
    try:
        fresh=timestamp(stock['calculated_at'])<=timestamp(now)<=timestamp(stock['valid_until'])
    except (KeyError,TypeError,ValueError):fresh=False
    status=stock.get(option_type.lower()+'_status','BLOCK') if fresh else 'BLOCK'
    reason=(stock.get('reasons') or {}).get(option_type,'Directional evidence unavailable.') if fresh else 'Directional evidence missing or stale; refresh before new risk.'
    if covered_policy not in {'BLOCK','WARNING'}:raise ValueError('Invalid covered-call DTV policy.')
    if verified_covered_call and option_type=='CE' and covered_policy=='WARNING' and status=='BLOCK':
        status='CAUTION';reason='Verified share-covered call policy: '+reason
    if status=='ALLOW':
        contexts=[('Sector',sector),('Market',market)]
        for label,value in contexts:
            try:valid=value and timestamp(value['calculated_at'])<=timestamp(now)<=timestamp(value['valid_until'])
            except (ValueError,TypeError,KeyError):valid=False
            if not valid or value.get(option_type.lower()+'_status') in {'BLOCK','CAUTION'}:
                status='CAUTION';reason=label+' confirmation conflicts or is unavailable; stock trend remains primary.';break
    if status=='BLOCK' and fresh and sector and sector.get(option_type.lower()+'_status')=='BLOCK':
        try:
            if timestamp(sector['calculated_at'])<=timestamp(now)<=timestamp(sector['valid_until']):
                reason += ' Sector trend confirms this directional veto.'
        except (KeyError,TypeError,ValueError):pass
    if status not in {'ALLOW','CAUTION','BLOCK'}:status='BLOCK'
    return dict(name='Directional trend risk',status={'ALLOW':'PASS','CAUTION':'WARNING','BLOCK':'BLOCK'}[status],
        decision=status,reason=reason,final_decision='NO NEW '+option_type+' SELL' if status=='BLOCK' else 'Existing checks required')


def log_decision(context, result, side, option_type, now):
    stock=context.get('stock') or {}
    payload={k:stock.get(k) for k in ('adx14','plus_di','minus_di','er5','er10','return_5d')}
    payload.update(timestamp=timestamp(now).isoformat(),symbol=context.get('symbol'),stock_trend=stock.get('market_regime'),
        sector_trend=(context.get('sector') or {}).get('market_regime','SECTOR UNAVAILABLE'),
        market_trend=(context.get('market') or {}).get('market_regime','UNAVAILABLE'),
        gap_pct=(stock.get('intraday') or {}).get('gap_pct'),original_trade_signal=option_type+' '+side,
        dtv_decision=result['decision'],final_trade_decision=result.get('final_decision','Existing checks required'),veto_reason=result['reason'])
    logger.info('TRADE_DTV %s',json.dumps(payload,sort_keys=True))


def table_cell(context, result):
    stock=context.get('stock') or {};sector=context.get('sector') or {}
    number=lambda v:'—' if v is None else f'{v:.2f}'
    tone={'BLOCK':'bad','CAUTION':'neutral','ALLOW':'good'}.get(result.get('decision'),'bad')
    return '<td><span class="ipo-badge '+tone+'">'+escape(result.get('decision','BLOCK'))+'</span><small>'+escape(stock.get('market_regime','UNAVAILABLE'))+'</small><details><summary>Trend details</summary>'+escape('Sector: '+sector.get('market_regime','SECTOR UNAVAILABLE')+' · ADX '+number(stock.get('adx14'))+' · ER5 '+number(stock.get('er5'))+' · '+result.get('final_decision','Refresh required')+' · As of '+str(stock.get('data_asof') or 'Unavailable'))+'</details></td>'


def render_trend_panel(context):
    if not context:return ''
    from nifty_options_engine.directional_ui import render_directional_panel,DTV_STYLE,DTV_SCRIPT
    stock=deepcopy(context.get('stock') or {});symbol=context.get('symbol','')
    stock['mmi_recommendation']='Stock trend first'
    panel=render_directional_panel(stock,{'directional_trend_veto':context['config']})
    panel=panel.replace('NIFTY Trend Strength &amp; Directional Risk','Trend Strength &amp; Directional Risk — '+escape(symbol))
    panel=panel.replace('Futures session VWAP','Volume-verified session VWAP').replace('MMI ', 'Context ')
    summary='Sector: '+(context.get('sector') or {}).get('market_regime','SECTOR UNAVAILABLE')+' · Market: '+(context.get('market') or {}).get('market_regime','UNAVAILABLE')
    slope=stock.get('normalized_ema_slope_pct')
    summary+=' · EMA slope (3 sessions): '+(f'{slope:+.2f}%' if slope is not None else 'Unavailable')
    script=DTV_SCRIPT.replace("MMI: ", "Context: ").replace("' · NIFTY '","' · Close '").replace("'nifty2-dtv-","'trade-dtv-")
    shared=(DTV_STYLE+panel+script).replace('dtv-', 'trade-dtv-').replace('>NIFTY Trend<','>Price Trend<')
    content='<details class="trade-dtv-detail"><summary><strong>Trend Strength &amp; Directional Risk — '+escape(symbol)+'</strong></summary><p>'+escape(summary)+'</p><div class="trade-dtv-grid">'+shared+'</div></details>'
    return content+'<style>.trade-dtv-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.trade-dtv-grid .trade-dtv-panel{grid-column:1;grid-row:1}.trade-dtv-grid .trade-dtv-charts{grid-column:2;grid-row:1}@media(max-width:900px){.trade-dtv-grid{grid-template-columns:1fr}.trade-dtv-grid .trade-dtv-charts{grid-column:1;grid-row:2}}</style>'
