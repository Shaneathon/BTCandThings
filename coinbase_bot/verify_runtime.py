"""Read-only Coinbase feed-size, freshness, accounting and activity verification."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from coinbase_bot.market_data import PRODUCTS
from coinbase_tracker.client import fetch,bot_inputs
from trading_bot.status_client import read_status
from trading_bot.verify_runtime import cbot_report

LIMIT=4_000_000


def tracker_report(path,now):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        observed,payload=db.execute('SELECT observed_at,payload FROM tracker_status WHERE id=1').fetchone()
    data=json.loads(payload)
    rows=[]
    for product in PRODUCTS:
        item=data.get('products',{}).get(product,{})
        source=item.get('bot_input',{})
        book_time=source.get('book_time')
        source_time=source.get('observed_at')
        rows.append(dict(product=product,bot_ready=item.get('bot_ready'),components=item.get('components'),
                         errors=item.get('errors'),candles=len(source.get('candles',[])),
                         book_age_seconds=round(now-book_time,1) if book_time is not None else None,
                         source_age_seconds=round(now-source_time,1) if source_time is not None else None,
                         meets_engine_time_limits=book_time is not None and source_time is not None
                         and 0<=now-book_time<=15 and 0<=now-source_time<=30))
    return dict(tracker_age_seconds=round(now-observed,1),stored_payload_bytes=len(payload.encode()),
                client_limit_bytes=LIMIT,below_client_size_limit=len(payload.encode())<=LIMIT,
                mode=data.get('mode'),orders_enabled=data.get('orders_enabled'),products=rows)


def activity_report(ledger,now,hours):
    if Path(ledger).name=='observed-v1.sqlite' and Path(ledger).with_name('PRODUCT-WALLETS-ACTIVE').is_file():
        root=Path(ledger).parent
        reports={product:activity_report(root/'products'/'baseline'/(product+'.sqlite'),now,hours) for product in PRODUCTS}
        states=Counter()
        for report in reports.values(): states.update(report['orders_created_in_period'])
        return dict(hours=hours,independent_product_wallets=reports,orders_created_in_period=dict(states),
                    trades_closed_in_period=sum(r['trades_closed_in_period'] for r in reports.values()))
    with sqlite3.connect(Path(ledger).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        row=db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()
        size=len(row[0].encode())
        orders=[dict(product=product,state=state,payload=json.loads(payload)) for product,state,payload in
                db.execute('SELECT product,state,payload FROM execution_orders')]
        trades=[json.loads(r[0]) for r in db.execute('SELECT payload FROM trades')]
        pending=[]
        for o in orders:
            if o['state']=='PROPOSED': pending.append(dict(product=o['product'],seconds_until_expiry=round(o['payload']['expires_at']-now,1)))
    return dict(hours=hours,status_payload_bytes=size,below_dashboard_size_limit=size<=LIMIT,
                orders_created_in_period=dict(Counter(o['state'] for o in orders if o['payload']['created_at']>=now-hours*3600)),
                trades_closed_in_period=sum(t['closed_at']>=now-hours*3600 for t in trades),pending=pending)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tracker-db',type=Path,default=Path('/var/lib/coin/research.sqlite'))
    p.add_argument('--ledger',type=Path,default=Path('/var/lib/cbot/observed-v1.sqlite'))
    p.add_argument('--hours',type=int,default=6)
    args=p.parse_args();now=time.time()
    for label,call in [('TRACKER',lambda:tracker_report(args.tracker_db,now)),
                       ('BOT_ACCOUNTING',lambda:cbot_report(args.ledger,now)),
                       ('ACTIVITY_AND_RESPONSE_SIZE',lambda:activity_report(args.ledger,now,args.hours))]:
        print(label)
        try: print(json.dumps(call(),indent=2,allow_nan=False))
        except Exception as error: print(json.dumps(dict(check_failed=type(error).__name__)))
    # Use exactly the production read-only clients and limits. Never print tokens.
    print('PRIVATE_LOCAL_API_CHECKS')
    for label,token_name,call in [
        ('Coin feed','COIN_READ_TOKEN',lambda token:bot_inputs(fetch('http://127.0.0.1:8767/status',token))),
        ('CBot dashboard','CBOT_READ_TOKEN',lambda token:read_status('http://127.0.0.1:8766/status',token,expected_venue='Coinbase Advanced'))]:
        token=os.environ.get(token_name,'')
        if not token:
            print(label,': NOT_CHECKED_PRIVATE_TOKEN_NOT_LOADED');continue
        try:
            data=call(token)
            print(label,': CLIENT_ACCEPTED_RESPONSE', '| ready products:'+str(sum(not v.get('error') for v in data.values())) if label=='Coin feed' else '| mode:'+str(data.get('operation_mode')))
        except Exception as error:
            print(label,': CLIENT_REJECTED_RESPONSE',type(error).__name__)
    print('SERVICES')
    for name in ('coin-collector','coin-status','coin-dashboard','cbot-paper','cbot-status','cbot-dashboard'):
        result=subprocess.run(['systemctl','is-active',name],capture_output=True,text=True,timeout=5)
        print(name,result.stdout.strip() or 'unknown')
    print('No service, strategy, wallet, or live-trading setting was changed.')

if __name__=='__main__': main()
