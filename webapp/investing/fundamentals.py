"""Manual provider boundary; no invented vendor endpoints or implicit networking."""
import csv
import io
import json
from typing import Protocol
from .schemas import Observation


class FundamentalsProvider(Protocol):
    def observations(self, isin: str, exchange: str) -> list[Observation]: ...


def import_observations(content: str, format: str) -> list[Observation]:
    if len(content.encode('utf-8')) > 2_000_000:
        raise ValueError('Import exceeds 2 MB.')
    content = content.lstrip('\ufeff')
    if format.lower() == 'json':
        rows = json.loads(content)
        if not isinstance(rows, list):
            raise ValueError('JSON import must be an array of observations.')
    elif format.lower() == 'csv':
        rows = list(csv.DictReader(io.StringIO(content)))
    else:
        raise ValueError('Only CSV or JSON evidence is supported.')
    if not rows or len(rows) > 10000:
        raise ValueError('Import must contain 1–10000 observations.')
    # Validate the complete batch before any persistence; never partially import.
    return [Observation.parse(row) for row in rows]
