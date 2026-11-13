"""Additive smart-closing metadata over the existing strategy/fill ledger.

No copied fills, broker calls, inferred condors or runtime settings imports.
A group is the existing strategy_id; pair IDs deterministically name its wings.
"""
from datetime import datetime, timezone
import json
from nifty_options_engine.ledger import NiftyStrategyRepository
from nifty_options_engine.analytics import strategy_performance
from smart_closer_config import configuration, positive


def now_text():
    return datetime.now(timezone.utc).isoformat()


class SmartCloserRepository(NiftyStrategyRepository):
    def ensure_schema(self):
        super().ensure_schema()
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS smart_closer_config (
                account_id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS smart_strategy_groups (
                strategy_group_id TEXT PRIMARY KEY REFERENCES nifty_strategies(strategy_id),
                account_id TEXT NOT NULL, broker TEXT NOT NULL DEFAULT 'ZERODHA',
                capital REAL, capital_source TEXT, capital_verified INTEGER NOT NULL DEFAULT 0,
                capital_snapshot_timestamp TEXT, capital_version INTEGER NOT NULL DEFAULT 0,
                target_pct REAL, target_locked INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED', reconciliation_day TEXT,
                last_checked_at TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS smart_strategy_pairs (
                pair_id TEXT PRIMARY KEY, strategy_group_id TEXT NOT NULL REFERENCES smart_strategy_groups(strategy_group_id),
                option_type TEXT NOT NULL, short_leg_id TEXT NOT NULL UNIQUE REFERENCES nifty_strategy_legs(leg_id),
                hedge_leg_id TEXT NOT NULL UNIQUE REFERENCES nifty_strategy_legs(leg_id),
                UNIQUE(strategy_group_id, option_type));
            CREATE TABLE IF NOT EXISTS smart_closer_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,
                strategy_group_id TEXT, action TEXT NOT NULL, actor TEXT NOT NULL,
                detail TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS smart_exit_intents (
                strategy_group_id TEXT PRIMARY KEY REFERENCES smart_strategy_groups(strategy_group_id),
                account_id TEXT NOT NULL, state TEXT NOT NULL, snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            ''')

    @staticmethod
    def _audit(db, account, group, action, actor, detail):
        if not actor:
            raise PermissionError('An authenticated actor is required for audited changes.')
        db.execute('INSERT INTO smart_closer_audit(account_id,strategy_group_id,action,actor,detail,created_at) VALUES(?,?,?,?,?,?)',
                   (account,group,action,actor,json.dumps(detail,allow_nan=False),now_text()))

    def config(self, account):
        with self.connect() as db:
            row=db.execute('SELECT body FROM smart_closer_config WHERE account_id=?',(account,)).fetchone()
        return configuration(json.loads(row[0]) if row else None)

    def save_config(self, account, values, *, actor):
        config=configuration(values)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._audit(db,account,None,'CONFIG_CHANGED',actor,config)
            db.execute('INSERT INTO smart_closer_config VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET body=excluded.body',
                       (account,json.dumps(config)))
        return config

    def register(self, account, strategy_id, mode):
        strategy=next((s for s in self.strategies(account,mode) if s['strategy_id']==strategy_id),None)
        if not strategy:
            raise ValueError('No account/mode-owned persisted strategy.')
        legs=strategy['legs']
        identities={(l.get('name') or l.get('underlying'),str(l['expiry'])[:10],l.get('product','NRML'),l.get('exchange','NFO')) for l in legs}
        if len(identities)!=1 or not next(iter(identities))[0]:
            raise ValueError('All group legs must share underlying, expiry, exchange and product.')
        pairs=[]
        for side in ('CE','PE'):
            wing=[l for l in legs if l['option_type']==side]
            if not wing: continue
            shorts=[l for l in wing if l['entry_side']=='SELL']
            hedges=[l for l in wing if l['entry_side']=='BUY']
            if len(wing)!=2 or len(shorts)!=1 or len(hedges)!=1:
                raise ValueError('Each pair needs exactly one short and one protective long.')
            short,hedge=shorts[0],hedges[0]
            if short['quantity']!=hedge['quantity'] or ((hedge['strike']-short['strike'])*(1 if side=='CE' else -1))<=0:
                raise ValueError('Invalid hedge geometry or quantities.')
            pairs.append((strategy_id+':'+side,strategy_id,side,short['leg_id'],hedge['leg_id']))
        if len(pairs)!=(2 if strategy['strategy_type']=='IRON_CONDOR' else 1):
            raise ValueError('Incomplete strategy membership.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT account_id FROM smart_strategy_groups WHERE strategy_group_id=?',(strategy_id,)).fetchone()
            if prior and prior[0]!=account: raise ValueError('Account mismatch.')
            db.execute('INSERT OR IGNORE INTO smart_strategy_groups(strategy_group_id,account_id,created_at) VALUES(?,?,?)',
                       (strategy_id,account,now_text()))
            for pair in pairs: db.execute('INSERT OR IGNORE INTO smart_strategy_pairs VALUES(?,?,?,?,?)',pair)
        return strategy_id

    def groups(self, account, mode):
        strategies={s['strategy_id']:s for s in self.strategies(account,mode)}
        with self.connect() as db:
            return [{**dict(row),'strategy':strategies[row['strategy_group_id']],
                     'pairs':[dict(p) for p in db.execute('SELECT * FROM smart_strategy_pairs WHERE strategy_group_id=?',(row['strategy_group_id'],))]}
                    for row in db.execute('SELECT * FROM smart_strategy_groups WHERE account_id=?',(account,))
                    if row['strategy_group_id'] in strategies]

    def verify_capital(self, account, group, mode, amount, source, *, actor, evidence, expected_version=0):
        amount=positive(amount)
        if source not in {'VERIFIED_ALLOCATION','INITIAL_BASKET_MARGIN','MANUAL_VERIFIED'} or not evidence:
            raise ValueError('Verified capital source and evidence required.')
        row=next((g for g in self.groups(account,mode) if g['strategy_group_id']==group),None)
        if not row: raise ValueError('Unknown owned strategy.')
        performance=strategy_performance(row['strategy'])
        if any(l['entered']!=l['quantity'] or l['invalid'] for l in performance['legs']):
            raise ValueError('Capital freezes only after every required entry quantity is filled.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM smart_exit_intents WHERE strategy_group_id=?',(group,)).fetchone():
                raise ValueError('Capital cannot change after an exit intent.')
            changed=db.execute('UPDATE smart_strategy_groups SET capital=?,capital_source=?,capital_verified=1,capital_snapshot_timestamp=?,capital_version=capital_version+1,status=\'REVIEW_REQUIRED\',reconciliation_day=NULL WHERE strategy_group_id=? AND account_id=? AND capital_version=?',
                (amount,source,now_text(),group,account,expected_version)).rowcount
            if changed!=1: raise ValueError('Capital is frozen; explicitly approve a versioned adjustment.')
            self._audit(db,account,group,'CAPITAL_VERIFIED',actor,dict(amount=amount,source=source,evidence=evidence,previous_version=expected_version))

    def set_target(self, account, group, pct, *, actor):
        config=self.config(account); pct=positive(pct)
        if not config['min_target_pct']<=pct<=config['max_target_pct']: raise ValueError('Target outside safe range.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM smart_exit_intents WHERE strategy_group_id=?',(group,)).fetchone():
                raise ValueError('Target cannot change during an exit.')
            changed=db.execute('UPDATE smart_strategy_groups SET target_pct=?,target_locked=1 WHERE strategy_group_id=? AND account_id=?',(pct,group,account)).rowcount
            if changed!=1: raise ValueError('Unknown owned group.')
            self._audit(db,account,group,'TARGET_LOCKED',actor,dict(profit_target_pct=pct))

    def save_reconciliation(self, account, results):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for result in results:
                status = result['status']
                intent = db.execute('SELECT state FROM smart_exit_intents WHERE strategy_group_id=? AND account_id=?',
                                    (result['strategy_group_id'], account)).fetchone()
                # Generic position reconciliation cannot reset an active exit or
                # declare it closed before the coordinator verifies final orders.
                if intent and status in {'ACTIVE_VERIFIED', 'PARTIALLY_CLOSED', 'CLOSED'}:
                    status = 'CLOSING'
                changed=db.execute('UPDATE smart_strategy_groups SET status=?,reconciliation_day=?,last_checked_at=? WHERE strategy_group_id=? AND account_id=?',
                    (status,result['reconciliation_day'],result['last_checked_at'],result['strategy_group_id'],account)).rowcount
                if changed!=1: raise ValueError('Unowned reconciliation result.')
                self._audit(db,account,result['strategy_group_id'],'RECONCILED','reconciliation',result)

    def fail_reconciliation(self, account, mode):
        with self.connect() as db:
            db.execute("UPDATE smart_strategy_groups SET status='REVIEW_REQUIRED',reconciliation_day=NULL WHERE account_id=? AND strategy_group_id IN (SELECT strategy_id FROM nifty_strategies WHERE mode=?)",(account,mode))
