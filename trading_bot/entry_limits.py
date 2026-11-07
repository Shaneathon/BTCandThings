"""Explicit entry-policy migration only; balances/positions/history unchanged."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from trading_bot.observed_paper import SETTINGS,LEGACY_SETTINGS


def migrate(path,rollback=False):
    old=json.dumps(LEGACY_SETTINGS,sort_keys=True);new=json.dumps(SETTINGS,sort_keys=True)
    expected,replacement=(new,old) if rollback else (old,new)
    with sqlite3.connect(path,timeout=15) as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]
        if json.loads(current)!=json.loads(expected): raise ValueError('Unexpected policy; do not reset or overwrite this ledger')
        db.execute('CREATE TABLE IF NOT EXISTS configuration_history(id INTEGER PRIMARY KEY,changed_at REAL,previous TEXT,current TEXT,reason TEXT)')
        cancelled=0
        if not rollback:
            cancelled=db.execute("UPDATE orders SET state='CANCELLED',result=? WHERE state='PROPOSED'",
                (json.dumps(dict(state='CANCELLED',reason='ENTRY_LIMIT_POLICY_CHANGED_BEFORE_FILL',filled_quantity='0',fees='0',total_cost='0',fills=[],simulated_only=True,live_orders_enabled=False)),)).rowcount
        db.execute('UPDATE settings SET payload=? WHERE id=1',(replacement,))
        db.execute('INSERT INTO configuration_history(changed_at,previous,current,reason) VALUES(?,?,?,?)',
                   (time.time(),current,replacement,'ROLLBACK_ENTRY_POLICY' if rollback else 'USER_REQUESTED_050_TO_5_PROPOSED_ENTRY_RANGE'))
    return dict(policy=json.loads(replacement),unfilled_proposals_cancelled_without_fee=cancelled,balances_and_positions_preserved=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--rollback',action='store_true')
    args=p.parse_args();print(json.dumps(migrate(args.ledger,args.rollback),indent=2))
