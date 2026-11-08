"""Read-only PBot activity presentation. Never evaluates or submits an order."""
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import time
import json
from zoneinfo import ZoneInfo
from trading_bot.core import time_of
from trading_bot.input_packet import read_packet
from trading_bot.dual_sandbox import MODELS

CENTRAL=ZoneInfo('America/Chicago')
TIME_FIELDS={'opened_at':'Filled (Central)','closed_at':'Settlement processed (Central)','settled_at':'Official settlement (Central)',
             'window_start':'Window opens (Central)','window_end':'Window closes (Central)',
             'observed_at':'First observed (Central)','quote_at':'Quote (Central)','signal_at':'Signal (Central)'}


def central(value):
    if value is None: return 'None yet'
    if isinstance(value,bool): return 'Unavailable'
    try:
        stamp=time_of(value) if isinstance(value,str) else float(value)
        return datetime.fromtimestamp(stamp,CENTRAL).strftime('%b %d, %Y %I:%M:%S %p %Z')
    except (ValueError,TypeError,OverflowError,OSError): return 'Unavailable'


def ago(value,now=None):
    if value is None: return 'None yet'
    now=time.time() if now is None else now
    elapsed=now-value
    if elapsed<0: return 'Clock ahead'
    if elapsed<60: return str(int(elapsed))+'s ago'
    if elapsed<3600: return str(int(elapsed//60))+'m ago'
    if elapsed<86400: return str(int(elapsed//3600))+'h '+str(int(elapsed%3600//60))+'m ago'
    return str(int(elapsed//86400))+'d ago'


def table_times(rows):
    return [{TIME_FIELDS.get(k,k):central(v) if k in TIME_FIELDS else v for k,v in row.items()} for row in rows]


def wallet_state(report,packet,health,now,paused=False,orders=()):
    a=report['account'];activity=report['activity'];stream=(a.get('market_pnl') or [{}])[0]
    if health['engine_age_seconds']<0 or health['engine_age_seconds']>30: return dict(state='ENGINE_STALE',severity='error')
    if health.get('input_error') or not health['input_fresh']: return dict(state='INPUT_BLOCKED',severity='error')
    if report.get('exit_order_states',{}).get('PROPOSED',0): return dict(state='EXIT_ORDER_PENDING',severity='info')
    if report.get('open_exit_triggers',0): return dict(state='EXIT_WAITING_FOR_BOOK',severity='warning')
    if report.get('automatic_entry_pause'): return dict(state='AUTOMATIC_ENTRY_PAUSE',severity='warning')
    if paused: return dict(state='ENTRIES_PAUSED',severity='warning')
    if a.get('halted_reason'): return dict(state='RISK_HALT',severity='warning')
    if activity['pending_orders']:
        overdue=any(now-o['expires_at']>10 for o in activity['pending_orders'])
        return dict(state='ORDER_PROCESSING_LATE' if overdue else 'ORDER_PENDING',severity='warning' if overdue else 'info')
    if activity['open_windows']:
        overdue=any(end<=now for end in activity['open_windows'])
        return dict(state='AWAITING_OFFICIAL_SETTLEMENT' if overdue else 'POSITION_OPEN',severity='info')
    if report.get('entry_budget_state')=='ROLLING_MARKET_ENTRY_LIMIT': return dict(state='ENTRY_QUOTA_REACHED',severity='info')
    if report.get('entry_budget_state')=='ENTRY_RETRY_SPACING': return dict(state='ENTRY_RETRY_WAIT',severity='info')
    if Decimal(activity.get('risk_capacity','1'))<=0: return dict(state='RISK_BUDGET_EXHAUSTED',severity='warning')
    markets=[m for m in packet.get('markets',[]) if m.get('asset')==stream.get('asset')
             and m.get('duration_seconds')==stream.get('duration_seconds')
             and time_of(m['window_start'])<=now<time_of(m['window_end'])]
    if not markets: return dict(state='NO_CURRENT_MARKET',severity='warning')
    m=max(markets,key=lambda m:m['window_start']);end=time_of(m['window_end']);remaining=end-now
    previous=[state for state,payload in orders if payload['plan']['market_slug']==m['market_slug']]
    # Multiple sequential entries are now permitted; old attempts are not a permanent blocker.
    result=dict(state='EVALUATING_BOOK_AND_EDGE',severity='info',market_slug=m['market_slug'],
                window_end=end,seconds_remaining=round(remaining,1))
    earliest=report.get('entry_timing',{}).get('earliest',90);latest_allowed=report.get('entry_timing',{}).get('latest',30)
    if remaining>min(earliest,stream.get('duration_seconds',earliest)): result['state']='WAITING_FOR_ENTRY_WINDOW';return result
    if report.get('entry_timing',{}).get('opening_wait') is not None:
        if now-time_of(m['window_start'])<report['entry_timing']['opening_wait']: result['state']='OPENING_WAIT';return result
        if remaining<=report['entry_timing']['close_cutoff']: result['state']='ENTRY_WINDOW_CLOSED';return result
    if remaining<latest_allowed: result['state']='ENTRY_WINDOW_CLOSED';return result
    if remaining<=report.get('entry_timing',{}).get('late_seconds',0): result['state']='LATE_REVERSAL_CHECK'
    signals=[p for p in packet.get('predictions',[]) if p.get('market_slug')==m['market_slug'] and p.get('model_version')==report.get('model_version')]
    latest=max(signals,key=lambda p:p['recorded_at']) if signals else None
    age=now-time_of(latest['recorded_at']) if latest else None
    result['signal_age_seconds']=round(age,1) if age is not None else None
    if age is None or not 0<=age<=90: result.update(state='WAITING_FOR_FRESH_SIGNAL',severity='warning');return result
    if report.get('model_version') in MODELS.values():
        paired=all(any(p.get('model_version')==version and p.get('market_slug')==m['market_slug']
                       and 0<=now-time_of(p['recorded_at'])<=90 for p in packet.get('predictions',[])) for version in MODELS.values())
        if not paired: result.update(state='WAITING_FOR_PAIRED_SIGNAL',severity='warning')
    return result


def enrich(path,result,now=None,input_path=Path('/var/lib/pbot-input/dual-sandbox.json')):
    now=time.time() if now is None else now
    error=None;packet={};size=None
    try:
        packet=read_packet(input_path);size=Path(input_path).stat().st_size
    except (OSError,ValueError) as exc:
        error='INPUT_TOO_LARGE' if str(exc)=='INPUT_TOO_LARGE' else 'INPUT_UNREADABLE_OR_INVALID'
    age=now-packet.get('exported_at',0)
    health=dict(engine_updated_at=result.get('observed_at'),engine_age_seconds=round(now-result.get('observed_at',0),1),
                input_updated_at=packet.get('exported_at'),input_age_seconds=round(age,1),input_bytes=size,
                input_fresh=error is None and 0<=age<=45,input_error=error or result.get('input_error'))
    last_filled=[];last_closed=[];last_order=[]
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        for name,report in result.get('portfolios',{}).items():
            positions=[json.loads(p[0]) for p in db.execute('SELECT payload FROM positions WHERE wallet=?',(name,))]
            orders=[(state,json.loads(payload)) for state,payload in db.execute('SELECT state,payload FROM orders WHERE wallet=?',(name,))]
            from trading_bot.performance_periods import breakdown
            report['performance_periods']=breakdown(positions,streams=[(r['asset'],r['duration_seconds']) for r in report['account'].get('market_pnl',[])],current_version=result.get('configuration',{}).get('version'))
            latest=max((p['opened_at'] for p in positions),default=None)
            closed=max((p['closed_at'] for p in positions if p.get('state')=='PAPER_CLOSED'),default=None)
            proposed=max((p['plan']['created_at'] for _,p in orders),default=None)
            pending=[dict(created_at=p['plan']['created_at'],expires_at=p['plan']['expires_at']) for state,p in orders if state=='PROPOSED']
            cash,high,_=db.execute('SELECT cash,high,halted FROM wallets WHERE name=?',(name,)).fetchone()
            cash,high=Decimal(cash),Decimal(high)
            exposure=sum((Decimal(p['cost']) for p in positions if p.get('state')=='PAPER_OPEN'),Decimal(0))
            reserved=sum((Decimal(p['reserve']) for state,p in orders if state=='PROPOSED'),Decimal(0))
            today=datetime.fromtimestamp(now,timezone.utc).date()
            daily=sum((Decimal(p['pnl']) for p in positions if p.get('state')=='PAPER_CLOSED' and datetime.fromtimestamp(p['closed_at'],timezone.utc).date()==today),Decimal(0))
            cfg=result.get('configuration',{})
            capacity=max(Decimal(0),min(Decimal(cfg.get('max_trade_cost','10')),cash-reserved,Decimal('10')-exposure-reserved,
                Decimal(cfg.get('max_daily_loss','100'))+daily-exposure-reserved,
                high*Decimal(cfg.get('max_drawdown','.10'))-(high-cash-exposure)-exposure-reserved))
            from trading_bot.trade_history import trade_row
            last_position=max(positions,key=lambda p:p['opened_at']) if positions else None
            last_entry=next(((state,record) for state,record in orders if last_position and record.get('entry_key',record['plan']['market_slug'])==last_position.get('entry_key',last_position['market_slug'])),None)
            last_trade=trade_row(name,last_position,last_entry[0] if last_entry else None,last_entry[1] if last_entry else None) if last_position else None
            report['activity']=dict(last_trade=last_trade,risk_capacity=str(capacity),last_filled_at=latest,last_settled_at=closed,last_order_proposed_at=proposed,
                filled_trade_count=len(positions),pending_orders=pending,
                open_windows=[p['window_end'] for p in positions if p.get('state')=='PAPER_OPEN'])
            if result.get('configuration',{}).get('max_entries_per_stream'):
                from trading_bot.entry_policy import reserve_slot
                stream=(report['account'].get('market_pnl') or [{}])[0]
                current=[m for m in packet.get('markets',[]) if m.get('asset')==stream.get('asset') and m.get('duration_seconds')==stream.get('duration_seconds') and time_of(m['window_start'])<=now<time_of(m['window_end'])]
                if current:
                    try: reserve_slot(db,name,max(current,key=lambda m:m['window_start']),now,result['configuration'])
                    except ValueError as error: report['entry_budget_state']=str(error)
            report['display_state']=wallet_state(report,packet,health,now,Path(path).with_name('STOP-OBSERVED').exists(),orders=orders)
            last_filled.append(latest);last_closed.append(closed);last_order.append(proposed)
    maximum=lambda values:max((v for v in values if v is not None),default=None)
    health.update(last_filled_at=maximum(last_filled),last_settled_at=maximum(last_closed),last_order_proposed_at=maximum(last_order))
    result['display_health']=health
    return result
