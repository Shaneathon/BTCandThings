"""Explicit entry-policy migration only; balances/positions/history unchanged."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from trading_bot.observed_paper import SETTINGS,LEGACY_SETTINGS,PREVIOUS_SETTINGS,RANGE_SETTINGS


def migrate(path,rollback=False,target_settings=None):
    target=SETTINGS if target_settings is None else target_settings
    if target_settings is not None:
        from trading_bot.market_band import BAND_SETTINGS,OLD_BAND_SETTINGS,V6_BAND_SETTINGS
        if target not in (SETTINGS,BAND_SETTINGS,OLD_BAND_SETTINGS,V6_BAND_SETTINGS): raise ValueError('Unreviewed target paper policy; preserving ledger')
    from trading_bot.market_band import OLD_BAND_SETTINGS,V6_BAND_SETTINGS
    accepted=(LEGACY_SETTINGS,RANGE_SETTINGS,PREVIOUS_SETTINGS,SETTINGS,OLD_BAND_SETTINGS,V6_BAND_SETTINGS)
    new=json.dumps(target,sort_keys=True)
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=15) as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]
        if not rollback and json.loads(current)==target:
            return dict(policy=target,policy_changed=False,unfilled_proposals_cancelled_without_fee=0,balances_and_positions_preserved=True)
        if rollback:
            prior=db.execute('SELECT previous,current FROM configuration_history ORDER BY id DESC LIMIT 1').fetchone()
            if json.loads(current)!=target or not prior or json.loads(prior[1])!=target:
                raise ValueError('Unexpected policy; do not reset or overwrite this ledger')
            replacement=prior[0]
            if json.loads(replacement) not in accepted: raise ValueError('Unknown rollback policy')
        else:
            if json.loads(current) not in accepted:
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
                   (time.time(),current,replacement,'ROLLBACK_ENTRY_POLICY' if rollback else 'USER_REQUESTED_PAPER_STRATEGY_POLICY'))
    return dict(policy=json.loads(replacement),policy_changed=True,unfilled_proposals_cancelled_without_fee=cancelled,balances_and_positions_preserved=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--rollback',action='store_true')
    p.add_argument('--profile',choices=('trailing','market-band'),default='trailing')
    args=p.parse_args()
    target=None
    if args.profile=='market-band':
        from trading_bot.market_band import BAND_SETTINGS
        target=BAND_SETTINGS
    print(json.dumps(migrate(args.ledger,args.rollback,target),indent=2))
