"""Append-only provenance and evaluation snapshots using existing SQLite patterns."""
import hashlib
import json
import sqlite3
from .schemas import Observation, timestamp


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class InvestingRepository:
    def __init__(self, path):
        self.path = path  # Constructor does not create or open a runtime database.

    def ensure_schema(self):
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS investing_v2_evidence(
                  account TEXT NOT NULL, digest TEXT NOT NULL, isin TEXT NOT NULL,
                  exchange TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(account,digest));
                CREATE INDEX IF NOT EXISTS investing_v2_identity ON investing_v2_evidence(account,isin,exchange);
                CREATE TABLE IF NOT EXISTS investing_v2_snapshots(
                  account TEXT NOT NULL, digest TEXT NOT NULL, isin TEXT NOT NULL,
                  exchange TEXT NOT NULL, evaluated_at TEXT NOT NULL, model_version TEXT NOT NULL,
                  data TEXT NOT NULL, PRIMARY KEY(account,digest));
            ''')

    def import_batch(self, account, observations):
        if not account:
            raise ValueError('Account scope required.')
        rows = []
        for observation in observations:
            item = Observation.parse(observation.to_dict())
            payload = canonical(item.to_dict())
            rows.append((account,hashlib.sha256(payload.encode()).hexdigest(),item.isin,item.exchange,payload))
        with sqlite3.connect(self.path) as conn:
            before = conn.total_changes
            conn.executemany('INSERT OR IGNORE INTO investing_v2_evidence VALUES(?,?,?,?,?)',rows)
            return conn.total_changes-before

    def observations(self, account, isin, exchange):
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute('SELECT data FROM investing_v2_evidence WHERE account=? AND isin=? AND exchange=?',
                                (account,isin,exchange)).fetchall()
        return [Observation.parse(json.loads(row[0])) for row in rows]

    def save_snapshot(self, account, isin, exchange, evaluated_at, model_version, result):
        if not account or not model_version:
            raise ValueError('Account and model version required.')
        stamp = timestamp(evaluated_at).isoformat()
        payload = canonical(dict(isin=isin,exchange=exchange,evaluated_at=stamp,model_version=model_version,result=result))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT OR IGNORE INTO investing_v2_snapshots VALUES(?,?,?,?,?,?,?)',
                         (account,digest,isin,exchange,stamp,model_version,payload))
        return digest

    def history(self, account, isin, exchange):
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute('SELECT data FROM investing_v2_snapshots WHERE account=? AND isin=? AND exchange=? ORDER BY evaluated_at DESC',
                                (account,isin,exchange)).fetchall()
        return [json.loads(row[0]) for row in rows]
