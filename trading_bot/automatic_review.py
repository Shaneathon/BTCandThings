"""Hourly, deterministic paper-only loss guard. Never modifies prediction models."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import time

POLICY=dict(version='PAPER_HOURLY_LOSS_GUARD_V1',lookback_hours=24,minimum_closed_trades=10,
            net_loss_trigger='20',pause_hours=6,
            scope='Current entry-policy cohort only; realized net results include modeled fees.',
            action='Pause new entries only; settlements continue. No strategy promotion or increased limits.')


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS automatic_entry_pauses (
      wallet TEXT PRIMARY KEY,created_at REAL NOT NULL,paused_until REAL NOT NULL,reason TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS automatic_reviews (id INTEGER PRIMARY KEY,reviewed_at REAL NOT NULL,payload TEXT NOT NULL);''')


def pause(db,wallet,now):
    row=db.execute('SELECT created_at,paused_until,reason FROM automatic_entry_pauses WHERE wallet=?',(wallet,)).fetchone()
    if row and now<row[0]: raise ValueError('AUTOMATIC_REVIEW_CLOCK_ROLLBACK')
    return dict(created_at=row[0],paused_until=row[1],reason=row[2]) if row and now<row[1] else None


def latest(db):
    row=db.execute('SELECT payload FROM automatic_reviews ORDER BY id DESC LIMIT 1').fetchone()
    return json.loads(row[0]) if row else None


def review(path,now=None):
    from trading_bot.observed_paper import SETTINGS,slots
    now=time.time() if now is None else now
    if not Path(path).is_file(): raise ValueError('Existing paper ledger required')
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=15) as db:
        # Validate identity before schema writes; never open or manage a live account.
        config=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        if config!=SETTINGS: raise ValueError('Unexpected paper configuration')
        stamp,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        snapshot=json.loads(payload)
        if (snapshot.get('operation_mode')!='OBSERVED_BOOK_PAPER' or snapshot.get('account',{}).get('live_orders_enabled') is not False
                or snapshot.get('account',{}).get('mode')!='PAPER' or not 0<=now-stamp<=60):
            raise ValueError('Paper engine identity/freshness check failed; no automatic actions')
        initialize(db)
        db.execute('BEGIN IMMEDIATE')
        prior=latest(db)
        if prior and now<prior['reviewed_at']: raise ValueError('Review clock rollback; no automatic actions')
        if prior and now-prior['reviewed_at']<1800:
            return dict(state='SKIPPED_RECENT_REVIEW',reviewed_at=prior['reviewed_at'])
        policy_row=db.execute('SELECT max(changed_at) FROM configuration_history').fetchone()
        policy_start=policy_row[0] or 0
        rows=[]
        for wallet in slots():
            control=db.execute('SELECT created_at,paused_until FROM automatic_entry_pauses WHERE wallet=?',(wallet,)).fetchone()
            active=pause(db,wallet,now)
            # After a pause, collect a new prospective sample. Never recycle the
            # same losses to prolong a pause or mix old $10 and current $5 entries.
            start=max(now-86400,policy_start,control[1] if control else 0)
            trades=[];excluded=0
            for encoded, in db.execute('SELECT payload FROM positions WHERE wallet=?',(wallet,)):
                p=json.loads(encoded)
                if p.get('state')!='PAPER_CLOSED' or not start<=p['opened_at']<=p['closed_at']<=now: continue
                if (p.get('entry_limits') or {}).get('version')!=SETTINGS['version']:
                    excluded+=1;continue
                value=Decimal(p['pnl'])
                if not value.is_finite(): raise ValueError('Invalid financial record')
                trades.append(value)
            net=sum(trades,Decimal(0));wins=sum(p>0 for p in trades)
            status='PAUSED' if active else 'INSUFFICIENT_NEW_TRADES' if len(trades)<POLICY['minimum_closed_trades'] else 'MONITORING'
            if not active and len(trades)>=POLICY['minimum_closed_trades'] and net<=-Decimal(POLICY['net_loss_trigger']):
                reason='At least 10 current-policy settled paper trades and net loss of $20 or more within 24 hours.'
                until=now+POLICY['pause_hours']*3600
                db.execute('INSERT INTO automatic_entry_pauses VALUES(?,?,?,?) ON CONFLICT(wallet) DO UPDATE SET created_at=excluded.created_at,paused_until=excluded.paused_until,reason=excluded.reason',
                           (wallet,now,until,reason))
                active=dict(created_at=now,paused_until=until,reason=reason);status='PAUSED_NEW'
            rows.append(dict(wallet=wallet,status=status,closed_trades=len(trades),wins=wins,net_pnl=str(net),cohort_start=start,
                excluded_other_entry_policies=excluded,entry_pause=active,
                previous_pause_expired=bool(control and control[1]<=now and (not prior or prior['reviewed_at']<control[1]))))
        report=dict(state='OK',reviewed_at=now,policy=POLICY,wallets=rows,live_orders_enabled=False,
                    note='A loss guard, not automatic strategy optimization. Paper profits do not establish live profitability.')
        db.execute('INSERT INTO automatic_reviews(reviewed_at,payload) VALUES(?,?)',(now,json.dumps(report,allow_nan=False)))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,default=Path('/var/lib/pbot/observed-v1.sqlite'))
    args=parser.parse_args()
    print(json.dumps(review(args.ledger),indent=2))
