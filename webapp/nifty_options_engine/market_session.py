"""NIFTY-only exchange calendar. Offline, versioned NSE calendar; unknown years fail closed."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
# NSE/FAOP/71777 and NSE/CMTR/71775, 12 Dec 2025.
CALENDAR_SOURCE = 'https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf'
HOLIDAYS = {'2026-'+day: name for day, name in [
    ('01-15','Maharashtra Municipal Election'),('01-26','Republic Day'),('03-03','Holi'),('03-26','Shri Ram Navami'),
    ('03-31','Shri Mahavir Jayanti'),('04-03','Good Friday'),
    ('04-14','Ambedkar Jayanti'),('05-01','Maharashtra Day'),('05-28','Bakri Id'),
    ('06-26','Muharram'),('09-14','Ganesh Chaturthi'),('10-02','Gandhi Jayanti'),
    ('10-20','Dussehra'),('11-10','Diwali-Balipratipada'),
    ('11-24','Guru Nanak Jayanti'),('12-25','Christmas')]}
# NSE/FAOP/76940: special continuous session, not regular weekday hours.
SPECIAL = {'2026-11-08': ('14:20','15:40')}


def get_nse_market_session(now_ist):
    now = now_ist.replace(tzinfo=IST) if now_ist.tzinfo is None else now_ist.astimezone(IST)
    day = now.date()
    def hours(d):
        if d.year != 2026:
            return None
        if d.isoformat() in SPECIAL:
            return SPECIAL[d.isoformat()]
        if d.weekday() >= 5 or d.isoformat() in HOLIDAYS:
            return ()
        # F&O normal close extended to 15:40 from August 2026.
        return ('09:15', '15:40' if d.isoformat() >= '2026-08-03' else '15:30')
    def neighbor(step, include=False):
        d = day if include else day+timedelta(days=step)
        for _ in range(370):
            h = hours(d)
            if h is None:
                return None
            if h:
                return d.isoformat()
            d += timedelta(days=step)
        return None
    h = hours(day)
    opened = bool(h and time.fromisoformat(h[0]) <= now.time().replace(tzinfo=None) < time.fromisoformat(h[1]))
    after = bool(h and now.time().replace(tzinfo=None) >= time.fromisoformat(h[1]))
    reason = ('CALENDAR_UNKNOWN' if h is None else 'NSE_HOLIDAY' if day.isoformat() in HOLIDAYS
              else 'WEEKEND' if not h else 'SPECIAL_SESSION' if opened and day.isoformat() in SPECIAL
              else 'REGULAR_SESSION' if opened else 'AFTER_MARKET' if after
              else 'PRE_OPEN' if time(9) <= now.time().replace(tzinfo=None) < time(9,15) else 'PRE_MARKET')
    return dict(status='MARKET_OPEN' if opened else 'SESSION_UNKNOWN' if h is None else 'MARKET_CLOSED',
        reason=reason, holiday_name=HOLIDAYS.get(day.isoformat()), regular_session_open=opened,
        new_entries_allowed=opened, last_trading_date=neighbor(-1,after),
        next_trading_date=neighbor(1,bool(h and not after and not opened)),
        session_date=day.isoformat(), open_time=h[0] if h else None, close_time=h[1] if h else None,
        special_session=day.isoformat() in SPECIAL, asof=now.isoformat(), source=CALENDAR_SOURCE)


def validate_market_data_freshness(market_session, spot_quote, daily_candles, intraday_candles, max_age=30):
    from .directional_trend import timestamp
    now = timestamp(market_session['asof'])
    def stamp(raw):
        try:
            return timestamp(raw) if raw else None
        except (ValueError, TypeError):
            return None
    quote = stamp(spot_quote.get('timestamp'))
    daily = stamp(daily_candles[-1].get('date')) if daily_candles else None
    intra = stamp(intraday_candles[-1].get('date')) if intraday_candles else None
    age = (now-quote).total_seconds() if quote else None
    expected = market_session.get('last_trading_date')
    daily_ok = daily is not None and daily.date().isoformat() == expected
    if not market_session['regular_session_open']:
        state = 'EXPECTED_PREVIOUS_SESSION' if daily_ok else 'MISSING'
        intraday_state = 'SESSION_CLOSED'
    else:
        spot_ok = age is not None and 0 <= age <= max_age and bool(spot_quote.get('last_price'))
        intra_ok = intra is not None and intra.date() == now.date() and 300 <= (now-intra).total_seconds() < 600
        state = 'FRESH' if spot_ok and intra_ok and daily_ok else 'STALE_DURING_MARKET'
        intraday_state = 'FRESH' if intra_ok else 'MISSING' if intra is None else 'STALE_DURING_MARKET'
    return dict(status=state, intraday_status=intraday_state, quote_timestamp=quote.isoformat() if quote else None,
                quote_age_seconds=age, daily_asof=daily.isoformat() if daily else None,
                intraday_asof=intra.isoformat() if intra else None, daily_valid=daily_ok)
