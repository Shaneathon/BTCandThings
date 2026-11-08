"""Explicit entry-policy migration only; balances/positions/history unchanged."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from trading_bot.observed_paper import SETTINGS,LEGACY_SETTINGS,PREVIOUS_SETTINGS


def migrate(path,rollback=False):
    new=json.dumps(SETTINGS,sort_keys=True)
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=15) as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]
        if not rollback and json.loads(current)==SETTINGS:
            return dict(policy=SETTINGS,policy_changed=False,unfilled_proposals_cancelled_without_fee=0,balances_and_positions_preserved=True)
        if rollback:
            prior=db.execute('SELECT previous,current FROM configuration_history ORDER BY id DESC LIMIT 1').fetchone()
            if json.loads(current)!=SETTINGS or not prior or json.loads(prior[1])!=SETTINGS:
                raise ValueError('Unexpected policy; do not reset or overwrite this ledger')
            replacement=prior[0]
            if json.loads(replacement) not in (LEGACY_SETTINGS,PREVIOUS_SETTINGS): raise ValueError('Unknown rollback policy')
        else:
            if json.loads(current) not in (LEGACY_SETTINGS,PREVIOUS_SETTINGS):
                saved=json.loads(current)
                raise ValueError('Unexpected policy; preserving ledger. Saved policy: '+json.dumps({key:saved.get(key) for key in ('version','min_trade_cost','max_trade_cost','target_trade_cost')},sort_keys=True))
            replacement=new
        db.execute('CREATE TABLE IF NOT EXISTS configuration_history(id INTEGER PRIMARY KEY,changed_at REAL,previous TEXT,current TEXT,reason TEXT)')
        cancelled=0
        if not rollback:
            cancelled=db.execute("UPDATE orders SET state='CANCELLED',result=? WHERE state='PROPOSED'",
                (json.dumps(dict(state='CANCELLED',reason='ENTRY_LIMIT_POLICY_CHANGED_BEFORE_FILL',filled_quantity='0',fees='0',total_cost='0',fills=[],simulated_only=True,live_orders_enabled=False)),)).rowcount
        db.execute('UPDATE settings SET payload=? WHERE id=1',(replacement,))
        db.execute('INSERT INTO configuration_history(changed_at,previous,current,reason) VALUES(?,?,?,?)',
                   (time.time(),current,replacement,'ROLLBACK_ENTRY_POLICY' if rollback else 'USER_REQUESTED_FIXED_150_PAPER_ENTRY_CAP'))
    return dict(policy=json.loads(replacement),policy_changed=True,unfilled_proposals_cancelled_without_fee=cancelled,balances_and_positions_preserved=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--rollback',action='store_true')
    args=p.parse_args();print(json.dumps(migrate(args.ledger,args.rollback),indent=2))
