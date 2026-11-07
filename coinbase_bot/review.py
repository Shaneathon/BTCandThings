"""Read-only paper performance attribution; no strategy changes or orders."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import statistics
import time


def trade_metrics(t):
    q=Decimal(t['quantity']);entry=q*Decimal(t['entry_price']);exit=q*Decimal(t['exit_price'])
    entry_fee=Decimal(t.get('entry_fees',str(Decimal(t['cost'])-entry)))
    exit_fee=Decimal(t.get('exit_fees',str(exit-Decimal(t['proceeds']))))
    net=Decimal(t['pnl']);gross=exit-entry;fees=entry_fee+exit_fee
    if abs(gross-fees-net)>Decimal('0.00000001'):
        raise ValueError('TRADE_FEE_PNL_DOES_NOT_RECONCILE')
    return dict(product=t['product_id'],exit_reason=t.get('exit_reason','UNKNOWN'),
                gross=gross,fees=fees,net=net,entry_notional=entry,exit_notional=exit,
                holding_seconds=t['closed_at']-t['opened_at'],closed_at=t['closed_at'],
                price_return_bps=(exit/entry-1)*10000)


def aggregate(rows):
    n=len(rows);total=lambda key:sum((r[key] for r in rows),Decimal(0))
    wins=[r['net'] for r in rows if r['net']>0];losses=[r['net'] for r in rows if r['net']<0]
    return dict(closed_trades=n,net_wins=len(wins),net_losses=len(losses),
                gross_pnl=str(total('gross')),estimated_fees=str(total('fees')),net_pnl=str(total('net')),
                average_net_pnl=str(total('net')/n) if n else None,
                average_win=str(sum(wins,Decimal(0))/len(wins)) if wins else None,
                average_loss=str(sum(losses,Decimal(0))/len(losses)) if losses else None,
                gross_positive_but_net_nonpositive=sum(r['gross']>0 and r['net']<=0 for r in rows),
                total_entry_notional=str(total('entry_notional')),
                median_hold_minutes=round(statistics.median(r['holding_seconds'] for r in rows)/60,2) if rows else None,
                median_price_return_bps=str(statistics.median(r['price_return_bps'] for r in rows)) if rows else None)


def review(path,now,hours):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        cfg=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        trades=[trade_metrics(json.loads(r[0])) for r in db.execute('SELECT payload FROM trades')]
        orders=[dict(state=s,plan=json.loads(p),result=json.loads(r) if r else None) for s,p,r in db.execute('SELECT state,payload,result FROM execution_orders')]
        decisions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM decision_journal WHERE observed_at>=?',(now-hours*3600,))]
    selected=[t for t in trades if t['closed_at']>=now-hours*3600]
    recent_orders=[o for o in orders if o['plan']['created_at']>=now-hours*3600]
    by=lambda key:{str(value):aggregate([r for r in selected if r[key]==value]) for value in sorted({r[key] for r in selected})}
    latencies=[]
    for o in recent_orders:
        if o['state']=='FILLED' and o['result']:
            r=o['result'];latencies.append(r['executed_at']-o['plan']['created_at'])
    fee=Decimal(cfg['fee_rate'])
    return dict(period_hours=hours,fee_basis=cfg.get('fee_basis','ESTIMATED'),
                fee_only_break_even_price_increase_bps=str(((1+fee)/(1-fee)-1)*10000),
                all_closed_history=aggregate(trades),period_closed_trades=aggregate(selected),
                by_product=by('product'),by_exit_reason=by('exit_reason'),
                recent_order_states=dict(Counter(o['state'] for o in recent_orders)),
                median_proposal_to_fill_seconds=round(statistics.median(latencies),2) if latencies else None,
                order_rejection_reasons=dict(Counter((o['result'] or {}).get('reason','UNKNOWN') for o in recent_orders if o['state'] in ('REJECTED','CANCELLED'))),
                decision_samples_by_reason=dict(Counter(d.get('reason',d.get('action','UNKNOWN')) for d in decisions)),
                notes=['Closed-trade attribution, not a counterfactual strategy backtest; open unrealized P/L excluded.',
                       'Fee tier/precision remain estimates. Gross returns already include observed bid/ask execution.',
                       'Decision counts are polling samples, not independent trade opportunities.',
                       'Six-hour samples are small; no strategy or risk setting was changed.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',type=Path,default=Path('/var/lib/cbot/observed-v1.sqlite'))
    p.add_argument('--hours',type=int,default=6)
    args=p.parse_args()
    if not 1<=args.hours<=168: p.error('Choose 1–168 hours')
    print(json.dumps(review(args.ledger,time.time(),args.hours),indent=2,allow_nan=False))

if __name__=='__main__': main()
