"""Read-only live paper verification. No tokens, exchange requests or service changes."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from trading_bot.core import time_of
from trading_bot.dual_sandbox import MODELS,RESEARCH_MODEL


def connect(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
    db.execute('BEGIN')
    return db


def reconcile(cash,positions,trades,initial='1000'):
    exposure=sum((Decimal(p['cost']) for p in positions if p.get('state','PAPER_OPEN')=='PAPER_OPEN'),Decimal(0))
    realized=sum((Decimal(t['pnl']) for t in trades),Decimal(0))
    delta=Decimal(cash)+exposure-Decimal(initial)-realized
    return dict(cash=str(cash),open_cost=str(exposure),realized_pnl=str(realized),
                accounting_difference=str(delta),accounting_ok=delta==0)


def input_report(path,now):
    if Path(path).stat().st_size>8_000_000: raise ValueError('INPUT_TOO_LARGE')
    data=json.loads(Path(path).read_text())
    lookup={m['market_slug']:m for m in data.get('markets',[])}
    summaries=[]
    current=data.get('requested_market')
    for label,model in [*MODELS.items(),('BTC15 research',RESEARCH_MODEL)]:
        rows=[p for p in data.get('predictions',[]) if p.get('model_version')==model and p.get('market_slug')==current]
        latest=max(rows,key=lambda p:p['recorded_at']) if rows else None
        market=lookup.get(current,{})
        summaries.append(dict(model=label,current_market=current,present=latest is not None,
            signal_age_seconds=round(now-time_of(latest['recorded_at']),1) if latest else None,
            seconds_remaining=round(time_of(market['window_end'])-now,1) if market.get('window_end') else None))
    proof=data.get('execution_evidence',{}).get('proofs',{})
    return dict(export_age_seconds=round(now-data.get('exported_at',0),1),
                fresh=0<=now-data.get('exported_at',0)<=45,controls=summaries,
                feed_errors=data.get('feed_errors',[]),mapping_corroboration=proof)


def pbot_report(path,now):
    with connect(path) as db:
        settings=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        observed,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        snapshot=json.loads(payload)
        wallets=[]
        for wallet,cash,high,halted in db.execute('SELECT name,cash,high,halted FROM wallets ORDER BY name'):
            positions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM positions WHERE wallet=?',(wallet,))]
            closed=[p for p in positions if p['state']=='PAPER_CLOSED']
            check=reconcile(cash,positions,closed,settings['initial_cash'])
            states=dict(db.execute('SELECT state,count(*) FROM orders WHERE wallet=? GROUP BY state',(wallet,)))
            expired=[]
            for slug,p in db.execute("SELECT market_slug,payload FROM orders WHERE wallet=? AND state='PROPOSED'",(wallet,)):
                expires=json.loads(p)['plan']['expires_at']
                if now-expires>10: expired.append(slug)
            reasons=Counter(r[0] for r in db.execute('SELECT reason FROM events WHERE wallet=? AND observed_at>=?',(wallet,now-1800)))
            fees_ok=all(Decimal(p['cost'])==sum((Decimal(f['quantity'])*Decimal(f['price'])+Decimal(f['fee']) for f in p['fills']),Decimal(0)) for p in positions)
            recent=[dict(market=s,reason=r,first_seen_at=t) for s,r,t in db.execute('SELECT market_slug,reason,observed_at FROM events WHERE wallet=? ORDER BY observed_at DESC LIMIT 3',(wallet,))]
            wallets.append(dict(wallet=wallet,**check,fill_costs_reconcile=fees_ok,halted=halted,
                                orders=states,overdue_pending_orders=expired,recent_distinct_reasons=dict(reasons),latest_history=recent))
        last_book=db.execute('SELECT observed_at,payload FROM books ORDER BY id DESC LIMIT 1').fetchone()
        book=None
        if last_book:
            raw=json.loads(last_book[1])
            normalized=raw.get('normalized',{}).get('UP',{})
            book=dict(observation_age_seconds=round(now-last_book[0],1),
                      contract=raw['market']['contract_slug'],last_exchange_transaction=normalized.get('exchange_last_transaction_at'))
        meta=dict(db.execute('SELECT key,value FROM meta'))
    return dict(mode=snapshot.get('operation_mode'),status_age_seconds=round(now-observed,1),
                live_orders_enabled=snapshot.get('account',{}).get('live_orders_enabled'),
                input_status=snapshot.get('input_status'),last_accepted_book=book,
                request_cooldown_seconds=max(0,round(meta.get('retry_until',0)-now,1)),wallets=wallets,
                note='Reason counts are distinct first-seen records, not retry counts or current status. Books are fetched only for eligible orders.')


def cbot_report(path,now):
    with connect(path) as db:
        settings=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        observed,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        snapshot=json.loads(payload)
        cash=db.execute('SELECT cash FROM account WHERE id=1').fetchone()[0]
        positions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM positions')]
        trades=[json.loads(r[0]) for r in db.execute('SELECT payload FROM trades')]
        overdue=[]
        for product,payload in db.execute("SELECT product,payload FROM execution_orders WHERE state='PROPOSED'"):
            if now-json.loads(payload)['expires_at']>10: overdue.append(product)
        states=dict(db.execute('SELECT state,count(*) FROM execution_orders GROUP BY state'))
    return dict(mode=snapshot.get('operation_mode'),status_age_seconds=round(now-observed,1),
                live_orders_enabled=snapshot.get('account',{}).get('live_orders_enabled'),
                **reconcile(cash,positions,trades,settings['initial_cash']),orders=states,
                overdue_pending_orders=overdue,decisions=[{k:d.get(k) for k in ('product_id','action','reason')} for d in snapshot.get('decisions',[])],
                fee_basis=snapshot.get('fee_basis'))


def public_book_report(input_path,ledger,now,bypass=False):
    """At most one unauthenticated GET, no retry, respect observed cooldown."""
    from urllib.parse import quote
    from urllib.request import Request,urlopen
    with connect(ledger) as db: budget=dict(db.execute('SELECT key,value FROM meta'))
    if budget.get('retry_until',0)>now or now-budget.get('last_request',0)<3:
        return dict(state='SKIPPED_TO_RESPECT_BOT_REQUEST_BUDGET',
                    retry_after_seconds=round(max(budget.get('retry_until',0)-now,3-(now-budget.get('last_request',0)),0),2))
    data=json.loads(Path(input_path).read_text())
    rows=[m for m in data.get('markets',[]) if m.get('market_slug')==data.get('requested_market')]
    if not rows: return dict(state='NO_CURRENT_BTC15_CONTRACT')
    contract=rows[0]['contract_slug']
    from trading_bot.book_request import request as make_request
    request=make_request(contract,bypass=bypass)
    try:
        with urlopen(request,timeout=5) as response:
            raw=response.read(4_000_001)
            if len(raw)>4_000_000: raise ValueError('RESPONSE_TOO_LARGE')
            payload=json.loads(raw);book=payload.get('marketData') or {}
            headers={name:response.headers.get(name) for name in ('Date','Age','Cache-Control','CF-Cache-Status')}
            from email.utils import parsedate_to_datetime
            from trading_bot.execution_audit import book_summary
            received=time.time()
            book_summary(payload,contract,received)
            current=rows[0]
            fresh=(headers['Date'] is not None and -5<=received-parsedate_to_datetime(headers['Date']).timestamp()<=5
                   and 0<=float(headers['Age'] or '0')<=5
                   and time_of(current['window_start'])<=received<time_of(current['window_end']))
            return dict(cache_bypass_requested=bypass,fresh_response_verified=fresh,state='PUBLIC_BOOK_OBSERVED',contract=contract,headers=headers,
                        contract_matches=book.get('marketSlug')==contract,book_state=book.get('state'),
                        bid_levels=len(book.get('bids') or []),offer_levels=len(book.get('offers') or []),
                        last_transaction_at=book.get('transactTime'))
    except Exception as error:
        return dict(state='PUBLIC_BOOK_CHECK_FAILED',error=type(error).__name__,http_status=getattr(error,'code',None))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('/var/lib/pbot-input/dual-sandbox.json'))
    parser.add_argument('--pbot',type=Path,default=Path('/var/lib/pbot/observed-v1.sqlite'))
    parser.add_argument('--cbot',type=Path,default=Path('/var/lib/cbot/observed-v1.sqlite'))
    parser.add_argument('--wait-for-budget',action='store_true',help='Wait up to 45 seconds for a quote budget slot; does not retry HTTP errors')
    parser.add_argument('--cache-probe',action='store_true',help='Only probe a unique-query fresh public book; does not modify services')
    parser.add_argument('--public-book',action='store_true',help='One public unauthenticated quote-header check, no retries')
    args=parser.parse_args();now=time.time()
    if args.cache_probe:
        deadline=time.monotonic()+45
        while True:
            result=public_book_report(args.input,args.pbot,time.time(),bypass=True)
            if result.get('state')!='SKIPPED_TO_RESPECT_BOT_REQUEST_BUDGET' or not args.wait_for_budget:
                break
            remaining=deadline-time.monotonic()
            retry=result.get('retry_after_seconds',3)
            if remaining<=0 or retry>remaining:
                print('Provider/request cooldown still active; services remain unchanged.',flush=True)
                break
            delay=min(max(retry+.15,.25),3,remaining)
            print('Waiting for quote request budget:',round(delay,2),'seconds',flush=True)
            time.sleep(delay)
        print(json.dumps(result,indent=2))
        if not result.get('fresh_response_verified'): raise SystemExit(1)
        return
    for label,callback in [('INPUT',lambda:input_report(args.input,now)),('PBOT',lambda:pbot_report(args.pbot,now)),('CBOT',lambda:cbot_report(args.cbot,now))]:
        print(label)
        try: print(json.dumps(callback(),indent=2,allow_nan=False))
        except Exception as error: print(json.dumps(dict(check_failed=type(error).__name__)))
    if args.public_book:
        print('PUBLIC BOOK HEADERS')
        try: print(json.dumps(public_book_report(args.input,args.pbot,time.time()),indent=2))
        except Exception as error: print(json.dumps(dict(check_failed=type(error).__name__)))
    print('SERVICES')
    for name in ('btc-collector','btc-challenger','btc-multiasset-research','pbot-sandbox-input.timer','pbot-paper','pbot-status','pbot-dashboard','coin-collector','cbot-paper','cbot-status','cbot-dashboard'):
        result=subprocess.run(['systemctl','is-active',name],capture_output=True,text=True,timeout=5)
        print(name,result.stdout.strip() or 'unknown')
    print('Read-only check complete. No service, account or trading rule was changed.')

if __name__=='__main__': main()
