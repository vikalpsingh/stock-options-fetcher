"""Source-independent financial observations. Missing is never zero."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import math
import re

STATUSES = {'VERIFIED', 'MISSING', 'STALE', 'NOT_APPLICABLE'}


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Evidence timestamps must include a timezone.')
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Observation:
    symbol: str
    isin: str
    exchange: str
    sector: str
    metric: str
    value: float | None
    unit: str
    period_end: str
    filing_date: str
    source: str
    fetched_at: str
    confidence: float
    status: str

    @classmethod
    def parse(cls, row):
        required = set(cls.__dataclass_fields__)
        if required - row.keys():
            raise ValueError('Missing fields: ' + ', '.join(sorted(required - row.keys())))
        item = {key: row[key] for key in required}
        for key in required - {'value', 'confidence'}:
            item[key] = str(item[key] or '').strip()
        for key in ('symbol', 'isin', 'exchange', 'status'):
            item[key] = item[key].upper()
        if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', item['isin']):
            raise ValueError('A valid ISIN identifier is required; symbol-only matching is forbidden.')
        if item['exchange'] not in {'NSE', 'BSE'} or item['status'] not in STATUSES:
            raise ValueError('Unsupported exchange or evidence status.')
        if any(not item[key] for key in ('symbol','sector','metric','unit','source')):
            raise ValueError('Symbol, sector, metric, unit and source are required.')
        if len(item['source']) > 2000 or len(item['metric']) > 100:
            raise ValueError('Evidence metadata is too long.')
        item['confidence'] = float(item['confidence'])
        if not math.isfinite(item['confidence']) or not 0 <= item['confidence'] <= 100:
            raise ValueError('Confidence must be finite and between 0 and 100.')
        value = item['value']
        item['value'] = None if value is None or value == '' else float(value)
        if item['value'] is not None and not math.isfinite(item['value']):
            raise ValueError('Financial values must be finite.')
        if (item['status'] in {'MISSING','NOT_APPLICABLE'}) != (item['value'] is None):
            raise ValueError('Missing/not-applicable values must be null; verified/stale values require a number.')
        period, filing = date.fromisoformat(item['period_end']), date.fromisoformat(item['filing_date'])
        fetched = timestamp(item['fetched_at'])
        if period > filing or filing > fetched.date():
            raise ValueError('Period, filing and fetched timestamps are out of sequence.')
        item['fetched_at'] = fetched.isoformat()
        return cls(**item)

    def state_at(self, now, max_period_age_days=450, max_fetch_age_days=90):
        now = timestamp(now)
        fetched = timestamp(self.fetched_at)
        if fetched > now or date.fromisoformat(self.filing_date) > now.date():
            return 'MISSING'  # No look-ahead in historical evaluation.
        if self.status != 'VERIFIED':
            return self.status
        if ((now.date()-date.fromisoformat(self.period_end)).days > max_period_age_days
                or (now-fetched).total_seconds() > max_fetch_age_days*86400):
            return 'STALE'
        return 'VERIFIED'

    def to_dict(self):
        return asdict(self)
