"""Read-only forward comparison with aligned entry cohort, separate ledgers."""
import json
from decimal import Decimal
from pathlib import Path
import sqlite3
import time
from coinbase_bot.review import trade_metrics,aggregate
from trading_bot.server import snapshot


def compare(baseline,challenger,now=None):
    now=time.time() if now is None else now
    with sqlite3.connect(Path(challenger).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        start=db.execute("SELECT value FROM experiment_metadata WHERE key='started_at'").fetchone()[0]
        stamp,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        child=json.loads(payload)
    if (child.get('account',{}).get('mode')!='PAPER' or child['account'].get('live_orders_enabled') is not False
            or child.get('strategy_version')!='COINBASE_FEE_FILTER_V1'):
        raise ValueError('Unexpected challenger mode or version')
    rows=[]
    for label,path in [('Baseline',baseline),('Fee filter V1',challenger)]:
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('BEGIN')
            trades=[json.loads(r[0]) for r in db.execute('SELECT payload FROM trades')]
            positions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM positions')]
        cohort=[trade_metrics(t) for t in trades if t['opened_at']>=start]
        rows.append(dict(experiment=label,**aggregate(cohort),
                         open_positions_entered_since_start=sum(p['opened_at']>=start for p in positions)))
    for row in rows:
        notional=Decimal(row['total_entry_notional'])
        row['net_return_on_entry_notional_percent']=str(100*Decimal(row['net_pnl'])/notional) if notional else None
    return dict(started_at=start,baseline_prior_risk_state_preserved=True,
                sample_status='INSUFFICIENT_FORWARD_TRADES' if any(r['closed_trades']<30 for r in rows) else 'DESCRIPTIVE_COMPARISON_ONLY',
                challenger_status_age_seconds=round(now-stamp,1),
                challenger_status_fresh=0<=now-stamp<=30,aligned_closed_trade_results=rows,
                challenger_market_pnl=child.get('market_pnl',[]),challenger_decisions=child.get('decisions',[]),
                challenger_order_states=child.get('order_states',{}),note=child.get('experiment_note'),
                cohort_rule='Only entries opened after challenger start. Earlier P/L and positions excluded. Baseline retains its prior cash/risk state; bankrolls are not perfectly matched. Open unrealized P/L excluded.')


def dashboard_snapshot(path):
    result=snapshot(path)
    challenger=Path(path).with_name('fee-filter-v1.sqlite')
    if Path(path).name=='observed-v1.sqlite' and challenger.is_file():
        try: result['paper_comparison']=compare(path,challenger)
        except Exception as error: result['paper_comparison_error']=type(error).__name__
    return result
