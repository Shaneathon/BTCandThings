"""Read-only six-hour PBot activity/risk/feed audit. No exchange requests."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import time
from trading_bot.core import time_of
from trading_bot.observed_paper import slots


def stamp(t):
    return datetime.fromtimestamp(t,timezone.utc).isoformat() if t is not None else None


def inspect(ledger,input_path,now,hours=6,source=None):
    from trading_bot.input_packet import read_packet
    input_bytes=Path(input_path).stat().st_size
    input_error=None
    try: data=read_packet(input_path)
    except (OSError,ValueError) as error:
        input_error='INPUT_TOO_LARGE' if str(error)=='INPUT_TOO_LARGE' else 'INPUT_UNREADABLE_OR_INVALID'
        data={}
    cutoff=now-hours*3600
    markets={m['market_slug']:m for m in data.get('markets',[])}
    rows=[]
    with sqlite3.connect(Path(ledger).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        observed,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        snapshot=json.loads(payload)
        for wallet,(asset,duration,model) in slots().items():
            cash,high,halted=db.execute('SELECT cash,high,halted FROM wallets WHERE name=?',(wallet,)).fetchone()
            orders=[dict(state=s,record=json.loads(p),result=json.loads(r) if r else {}) for s,p,r in db.execute('SELECT state,payload,result FROM orders WHERE wallet=?',(wallet,))]
            recent=[o for o in orders if o['record']['plan']['created_at']>=cutoff]
            positions=[json.loads(p[0]) for p in db.execute('SELECT payload FROM positions WHERE wallet=?',(wallet,))]
            opened=[p for p in positions if p['state']=='PAPER_OPEN']
            waiting=[]
            for p in opened:
                m=markets.get(p['market_slug'],{})
                waiting.append(dict(market=p['market_slug'],minutes_past_window_end=round((now-p['window_end'])/60,1),
                    exported_settlement_status=m.get('settlement_status','MISSING_FROM_INPUT'),
                    official_winner=m.get('official_winner'),cost=p['cost']))
            current=[m for m in markets.values() if m.get('asset')==asset and m.get('duration_seconds')==duration
                     and time_of(m['window_start'])<=now<time_of(m['window_end'])]
            m=max(current,key=lambda m:m['window_start']) if current else None
            signals=[p for p in data.get('predictions',[]) if p.get('model_version')==model and m and p.get('market_slug')==m['market_slug']]
            latest=max(signals,key=lambda p:p['recorded_at']) if signals else None
            signal_age=now-time_of(latest['recorded_at']) if latest else None
            remaining=time_of(m['window_end'])-now if m else None
            skips=dict(db.execute('SELECT reason,count(*) FROM events WHERE wallet=? AND observed_at>=? GROUP BY reason ORDER BY count(*) DESC',(wallet,cutoff)))
            paired=None
            if wallet in ('Champion','Challenger B') and m:
                from trading_bot.dual_sandbox import MODELS
                paired={name:any(p.get('model_version')==version and p.get('market_slug')==m['market_slug'] and
                                0<=now-time_of(p['recorded_at'])<=90 for p in data.get('predictions',[]))
                        for name,version in MODELS.items()}
            cfg=snapshot.get('configuration',{})
            if cfg.get('entry_strategy')=='MARKET_BAND':
                eligible=m is not None and now-time_of(m['window_start'])>=cfg['opening_wait_seconds'] and remaining>(cfg['close_cutoff_15m'] if duration==900 else cfg['close_cutoff_5m'])
            else: eligible=remaining is not None and cfg.get('entry_seconds_remaining',[30,90])[0]<=remaining<=min(cfg.get('entry_seconds_remaining',[30,90])[1],duration)
            current_state=('RISK_HALT' if halted else 'OPEN_POSITION_BLOCKS_NEW_ENTRIES' if opened else
                           'NO_CURRENT_MARKET' if not m else 'WAITING_FOR_ENTRY_WINDOW' if not eligible else
                           'NO_FRESH_SIGNAL' if signal_age is None or not 0<=signal_age<=90 else
                           'MISSING_PAIRED_CONTROL_SIGNAL' if paired and not all(paired.values()) else 'IN_ENTRY_WINDOW_CHECK_BOOK_AND_EDGE')
            fills=[o for o in recent if Decimal(o['result'].get('filled_quantity','0'))>0]
            rows.append(dict(wallet=wallet,current_state=current_state,cash=cash,halted=halted,
                orders_created_in_period=len(recent),order_states_in_period=dict(Counter(o['state'] for o in recent)),
                filled_orders_in_period=len(fills),
                settled_positions_in_period=sum(p['state']=='PAPER_CLOSED' and p['closed_at']>=cutoff for p in positions),
                last_order_at=stamp(max((o['record']['plan']['created_at'] for o in orders),default=None)),
                current_signal_age_seconds=round(signal_age,1) if signal_age is not None else None,
                seconds_remaining=round(remaining,1) if remaining is not None else None,paired_controls_fresh=paired,
                open_positions=waiting,
                rejected_order_reasons=dict(Counter(o['result'].get('reason','UNKNOWN') for o in recent if o['state']=='REJECTED')),
                distinct_first_seen_skip_reasons=skips))
        budget=dict(db.execute('SELECT key,value FROM meta'))
        lastbook=db.execute('SELECT observed_at FROM books ORDER BY id DESC LIMIT 1').fetchone()
    report=dict(checked_at=stamp(now),period_hours=hours,status_age_seconds=round(now-observed,1),
                input_bytes=input_bytes,input_rejected_reason=input_error,
                input_age_seconds=round(now-data.get('exported_at',0),1),
                live_orders_enabled=snapshot.get('account',{}).get('live_orders_enabled'),
                pause_file_present=Path(ledger).with_name('STOP-OBSERVED').exists(),
                feed_errors=data.get('feed_errors',[]),
                quote_cooldown_seconds=round(max(0,budget.get('retry_until',0)-now),1),
                last_accepted_book_age_seconds=round(now-lastbook[0],1) if lastbook else None,
                wallets=rows,
                note='Skip counts count distinct first-seen market/reason records, not every polling attempt. No exchange requests or rule changes.')
    if source:
        with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM collector_status WHERE singleton=1').fetchone()
            state=json.loads(row[0]) if row else {}
        report['collector']=dict(observed_at=state.get('observed_at'),streams={k:{field:v.get(field) for field in
            ('collection_ready','paused_reason','metadata_ready','quote_status','quote_http_status','market_errors')} for k,v in state.get('streams',{}).items()},
            settlements=state.get('settlements'),cloud_storage=state.get('cloud_storage'))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',type=Path,default=Path('/var/lib/pbot/observed-v1.sqlite'))
    p.add_argument('--input',type=Path,default=Path('/var/lib/pbot-input/dual-sandbox.json'))
    p.add_argument('--source',type=Path,default=Path('/var/lib/btcandthings-research/research.sqlite'))
    p.add_argument('--hours',type=int,default=6)
    args=p.parse_args()
    if not 1<=args.hours<=48: p.error('Choose 1–48 hours')
    print(json.dumps(inspect(args.ledger,args.input,time.time(),args.hours,args.source),indent=2,allow_nan=False))

if __name__=='__main__': main()
