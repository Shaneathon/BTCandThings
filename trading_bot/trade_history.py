"""Authenticated caller's read-only, bounded PBot fill history; no proposals-as-fills."""
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import time


def trade_row(wallet,p,order_state=None,order_record=None):
    from trading_bot.performance_periods import label
    closed=p.get('state')=='PAPER_CLOSED'
    payout=p.get('payout')
    result=('WON' if Decimal(str(payout))>0 else 'LOST') if closed and payout is not None else 'OPEN'
    return dict(entry_policy=label(p),wallet=wallet,market_slug=p.get('market_slug'),asset=p.get('asset'),duration_seconds=p.get('duration_seconds'),
                model_version=p.get('model_version'),side=p.get('side'),quantity=p.get('quantity'),entry_price=p.get('entry_price'),
                fees=p.get('fees'),cost=p.get('cost'),result=result,payout=payout,pnl=p.get('pnl'),
                opened_at=p.get('opened_at'),closed_at=p.get('closed_at'),window_start=p.get('window_start'),window_end=p.get('window_end'),
                order_state=order_state,requested_quantity=(order_record or {}).get('plan',{}).get('quantity'),order_id=p.get('order_id'))


def page(path,wallet='*',number=1,limit=50,as_of=None,now=None):
    now=time.time() if now is None else now
    as_of=now if as_of is None else as_of
    if type(number) is not int or number<1 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('Invalid history page or limit')
    if isinstance(as_of,bool) or not math.isfinite(as_of) or not 0<=as_of<=now+5:
        raise ValueError('Invalid history anchor')
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallets'").fetchone():
            raise LookupError('History unavailable for this ledger')
        config=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        if config.get('version') not in ('OBSERVED_PAPER_V1','OBSERVED_PAPER_V2_050_5','OBSERVED_PAPER_V3_FIXED_150'): raise LookupError('Wrong ledger version')
        if wallet!='*' and not db.execute('SELECT 1 FROM wallets WHERE name=?',(wallet,)).fetchone():
            raise ValueError('Unknown wallet')
        clauses=["CAST(json_extract(p.payload,'$.opened_at') AS REAL)<=?"]
        params=[as_of]
        if wallet!='*': clauses.append('p.wallet=?');params.append(wallet)
        where=' AND '.join(clauses)
        total=db.execute('SELECT count(*) FROM positions p WHERE '+where,params).fetchone()[0]
        pages=max(1,(total+limit-1)//limit);number=min(number,pages)
        rows=db.execute('''SELECT p.wallet,p.payload,o.state,o.payload FROM positions p LEFT JOIN orders o
          ON p.wallet=o.wallet AND p.market_slug=o.market_slug WHERE '''+where+'''
          ORDER BY CAST(json_extract(p.payload,'$.opened_at') AS REAL) DESC,p.wallet,p.market_slug LIMIT ? OFFSET ?''',
          [*params,limit,(number-1)*limit]).fetchall()
    result=[trade_row(w,json.loads(p),state,json.loads(o) if o else None) for w,p,state,o in rows]
    return dict(account=dict(mode='PAPER',venue='Polymarket US',live_orders_enabled=False),wallet=wallet,
                as_of=as_of,page=number,page_count=pages,page_size=limit,total_filled_trades=total,trades=result,
                note='Observed-price ledger only. Partial fills are trades; unfilled proposals are excluded. New fills after anchor appear on refresh.')
