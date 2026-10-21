"""Shared exchange-time helpers. Naive broker timestamps mean IST, never host time."""
from datetime import datetime
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")

def app_now_ist():
    return datetime.now(APP_TIMEZONE)

def parse_kite_timestamp(value):
    stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return stamp.replace(tzinfo=APP_TIMEZONE) if stamp.tzinfo is None else stamp.astimezone(APP_TIMEZONE)

def to_ist(value):
    return parse_kite_timestamp(value)

def get_quote_age_seconds(quote, now=None):
    # Last-trade time is not the timestamp of the current quote packet.
    try:
        return (to_ist(now or app_now_ist())-parse_kite_timestamp(quote.get('timestamp'))).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None

def is_quote_fresh(quote, max_age_seconds=120, now=None):
    age=get_quote_age_seconds(quote, now)
    return age is not None and 0 <= age <= max_age_seconds
