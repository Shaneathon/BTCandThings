"""Four-coin public Coinbase research archive. No account or order endpoints."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import time

from coinbase_bot.market_data import PRODUCTS,BASE,get_json,positive,timestamp,momentum

APP_ID=1129271630


_last_request=None

def paced_get_json(url,params=None):
    """Identify public requests through the existing client, at <=4 starts/sec."""
    global _last_request
    now=time.monotonic()
    if _last_request is not None:
        delay=.25-(now-_last_request)
        if delay>0: time.sleep(delay)
    _last_request=time.monotonic()
    return get_json(url,params)


class Store:
    def __init__(self,path):
        if str(path)!=':memory:' and Path(path).exists() and Path(path).stat().st_size:
            with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as check:
                if check.execute('PRAGMA application_id').fetchone()[0]!=APP_ID:
                    raise ValueError('Not a Coinbase tracker database; no changes made')
        self.db=sqlite3.connect(path,timeout=15)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute(f'PRAGMA application_id={APP_ID}')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS observations (product TEXT,component TEXT,observed_at REAL,payload TEXT,PRIMARY KEY(product,component,observed_at));
          CREATE TABLE IF NOT EXISTS candles (product TEXT,start INTEGER,payload TEXT,PRIMARY KEY(product,start));
          CREATE TABLE IF NOT EXISTS trades (product TEXT,trade_id TEXT,payload TEXT,PRIMARY KEY(product,trade_id));
          CREATE TABLE IF NOT EXISTS features (product TEXT,candle_end INTEGER,observed_at REAL,payload TEXT,PRIMARY KEY(product,candle_end));
          CREATE TABLE IF NOT EXISTS tracker_status (id INTEGER PRIMARY KEY,observed_at REAL,payload TEXT);
        ''')
    def close(self): self.db.close()


def metadata(payload,product):
    if (payload.get('product_id')!=product or payload.get('product_type')!='SPOT'
            or payload.get('base_currency_id')!=product.split('-')[0] or payload.get('quote_currency_id')!='USD'):
        raise ValueError('PRODUCT_IDENTITY')
    for field in ('base_increment','quote_increment','base_min_size','quote_min_size'):
        positive(payload[field])
    return payload


def candles(payload,now):
    rows={}
    for row in payload['candles']:
        start=int(row['start'])
        if start%60: raise ValueError('UNALIGNED_CANDLE')
        if start+60>now: continue
        o,h,l,c=(positive(row[k]) for k in ('open','high','low','close'))
        positive(row['volume'],zero=True)
        if h<max(o,c,l) or l>min(o,c,h): raise ValueError('INVALID_OHLC')
        normalized={k:row[k] for k in ('start','open','high','low','close','volume')}
        normalized['start']=start
        if start in rows and rows[start]!=normalized: raise ValueError('CONFLICTING_CANDLE')
        rows[start]=normalized
    return [rows[t] for t in sorted(rows)]


def book(payload,product,now):
    value=payload['pricebook']
    if value.get('product_id')!=product: raise ValueError('BOOK_IDENTITY')
    source=timestamp(value['time'])
    if not 0<=now-source<=15: raise ValueError('STALE_OR_FUTURE_BOOK')
    sides={}
    for side in ('bids','asks'):
        levels=value[side]
        if not levels: raise ValueError('EMPTY_BOOK')
        normalized=[dict(price=str(positive(l['price'])),size=str(positive(l['size']))) for l in levels]
        prices=[Decimal(l['price']) for l in normalized]
        if prices!=sorted(prices,reverse=side=='bids') or len(set(prices))!=len(prices):
            raise ValueError('UNSORTED_OR_DUPLICATE_BOOK')
        sides[side]=normalized
    bid,ask=Decimal(sides['bids'][0]['price']),Decimal(sides['asks'][0]['price'])
    if bid>ask: raise ValueError('CROSSED_BOOK')
    bid_size=sum((Decimal(l['size']) for l in sides['bids']),Decimal(0))
    ask_size=sum((Decimal(l['size']) for l in sides['asks']),Decimal(0))
    return dict(product_id=product,book_time=source,**sides,bid=str(bid),ask=str(ask),
                spread_bps=float((ask-bid)/((ask+bid)/2)*10000),
                bid_depth_base=str(bid_size),ask_depth_base=str(ask_size),
                depth_imbalance=float((bid_size-ask_size)/(bid_size+ask_size)))


def trades(payload,product,now):
    result={}
    for row in payload['trades']:
        if row.get('product_id')!=product or not str(row.get('trade_id','')): raise ValueError('TRADE_IDENTITY')
        if timestamp(row['time'])>now: raise ValueError('FUTURE_TRADE')
        positive(row['price']);positive(row['size'])
        if row.get('side') not in ('BUY','SELL'): raise ValueError('UNKNOWN_TRADE_SIDE')
        normalized={k:row[k] for k in ('trade_id','product_id','time','price','size','side')}
        identifier=str(row['trade_id'])
        if identifier in result and result[identifier]!=normalized: raise ValueError('CONFLICTING_TRADE')
        result[identifier]=normalized
    return list(result.values())


def indicators(rows,now):
    if len(rows)<60: return dict(ready=False,reason='INSUFFICIENT_CANDLES')
    recent=rows[-120:]
    if not 0<=now-(recent[-1]['start']+60)<=120: return dict(ready=False,reason='STALE_CANDLES')
    if any(b['start']-a['start']!=60 for a,b in zip(recent,recent[1:])):
        return dict(ready=False,reason='CANDLE_GAPS')
    signal=momentum({'candles':recent})
    closes=[float(r['close']) for r in recent]
    changes=[b-a for a,b in zip(closes,closes[1:])]
    gains=sum(max(0,c) for c in changes[-14:])/14
    losses=sum(max(0,-c) for c in changes[-14:])/14
    rsi=100-100/(1+gains/losses) if losses else (100 if gains else 50)
    returns=[math.log(b/a) for a,b in zip(closes,closes[1:])][-20:]
    mean=sum(returns)/len(returns)
    vol=math.sqrt(sum((r-mean)**2 for r in returns)/(len(returns)-1))
    true_ranges=[max(float(b['high'])-float(b['low']),abs(float(b['high'])-float(a['close'])),
                     abs(float(b['low'])-float(a['close']))) for a,b in zip(recent,recent[1:])][-14:]
    volume=sum(float(r['volume']) for r in recent)
    vwap=sum((float(r['high'])+float(r['low'])+float(r['close']))/3*float(r['volume']) for r in recent)/volume if volume else None
    if not all(math.isfinite(value) for value in (rsi,vol,sum(true_ranges),volume)) or (vwap is not None and not math.isfinite(vwap)):
        raise ValueError('UNREPRESENTABLE_INDICATOR')
    return dict(ready=True,**signal,rsi14=rsi,atr14=sum(true_ranges)/len(true_ranges),
                volatility_1m=vol,candle_vwap_approx=vwap,volume_base=volume,
                change_5m=closes[-1]/closes[-6]-1,change_15m=closes[-1]/closes[-16]-1,
                observed_candle_close=recent[-1]['start']+60)


def collect(store,get=paced_get_json,now=None):
    fixed=now is not None
    started=time.time() if now is None else now
    report=dict(mode='RESEARCH_TRACKER',venue='Coinbase Advanced',observed_at=started,products={},orders_enabled=False)
    for product in PRODUCTS:
        state=dict(product_id=product,components={},errors={},latency_ms={},bot_ready=False)
        report['products'][product]=state
        end=int(started)//60*60
        tasks=[('metadata',BASE+'/products/'+product,None),
               ('candles',BASE+'/products/'+product+'/candles',dict(start=str(end-120*60),end=str(end),granularity='ONE_MINUTE',limit='120')),
               ('book',BASE+'/product_book',dict(product_id=product,limit='20')),
               ('trades',BASE+'/products/'+product+'/ticker',dict(limit='100'))]
        for kind,url,params in tasks:
            observed=started if fixed else time.time()
            requested=time.monotonic()
            try:
                payload=get(url,params)
                state['latency_ms'][kind]=round((time.monotonic()-requested)*1000,3)
                observed=started if fixed else time.time()
                normalized={'metadata':lambda:metadata(payload,product),'candles':lambda:candles(payload,observed),
                            'book':lambda:book(payload,product,observed),'trades':lambda:trades(payload,product,observed)}[kind]()
                with store.db:
                    store.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)',(product,kind,observed,json.dumps({'request_url':url,'parameters':params,'latency_ms':state['latency_ms'][kind],'response':payload},allow_nan=False)))
                    if kind=='candles':
                        store.db.executemany('INSERT INTO candles VALUES (?,?,?) ON CONFLICT(product,start) DO UPDATE SET payload=excluded.payload',
                            [(product,r['start'],json.dumps(r,allow_nan=False)) for r in normalized])
                    if kind=='trades':
                        for row in normalized:
                            encoded=json.dumps(row,sort_keys=True,allow_nan=False)
                            old=store.db.execute('SELECT payload FROM trades WHERE product=? AND trade_id=?',(product,str(row['trade_id']))).fetchone()
                            if old and old[0]!=encoded: raise ValueError('CONFLICTING_ARCHIVED_TRADE')
                            store.db.execute('INSERT OR IGNORE INTO trades VALUES (?,?,?)',(product,str(row['trade_id']),encoded))
                state[kind]=normalized
                state['components'][kind]='OK'
            except Exception as exc:
                state['errors'][kind]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                state['components'][kind]='UNAVAILABLE'
        observed=started if fixed else time.time()
        rows=state.get('candles',[])
        try:
            state['indicators']=indicators(rows,observed)
        except Exception as exc:
            state['indicators']={'ready':False,'reason':'INDICATOR_ERROR'}
            state['errors']['indicators']=type(exc).__name__
        state['quality']=dict(candles=len(rows),candle_gap_count=sum(b['start']-a['start']!=60 for a,b in zip(rows,rows[1:])),
                              last_close_age_seconds=observed-(rows[-1]['start']+60) if rows else None,
                              sampled_trades=len(state.get('trades',[])),trade_coverage='LATEST_100_SAMPLED_NOT_COMPLETE')
        if state['indicators']['ready']:
            with store.db:
                store.db.execute('INSERT OR IGNORE INTO features VALUES (?,?,?,?)',(product,state['indicators']['candle_end'],observed,json.dumps(state['indicators'],allow_nan=False)))
        meta=state.get('metadata',{})
        tradable=(str(meta.get('status','')).upper()=='ONLINE' and meta.get('trading_disabled') is False
                  and not any(meta.get(k) for k in ('is_disabled','cancel_only','post_only','auction_mode','view_only')))
        state['bot_ready']=bool(tradable and state['indicators']['ready'] and 'book' in state)
        if state['bot_ready']:
            b=state['book']
            state['bot_input']=dict(product_id=product,metadata=meta,candles=rows,observed_at=observed,book_time=b['book_time'],
                bid=b['bid'],ask=b['ask'],bid_size=b['bids'][0]['size'],ask_size=b['asks'][0]['size'])
    report['observed_at']=started if fixed else time.time()
    report['all_products_ready']=all(p['bot_ready'] for p in report['products'].values())
    report['all_components_ready']=all(not p['errors'] for p in report['products'].values())
    with store.db:
        store.db.execute('INSERT INTO tracker_status VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',
                         (report['observed_at'],json.dumps(report,allow_nan=False)))
    return report


def snapshot(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM tracker_status WHERE id=1').fetchone()
        if not row: raise ValueError('No collection pass yet')
        return json.loads(row[0])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--loop',action='store_true')
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--interval',type=int,default=15,help='REST sampling seconds, minimum 5; not a complete tick stream')
    args=parser.parse_args()
    if args.interval<5: parser.error('Minimum interval is five seconds')
    if args.status:
        data=snapshot(args.db)
        print(json.dumps(data))
        raise SystemExit(0 if data['all_products_ready'] and data['all_components_ready'] and 0<=time.time()-data['observed_at']<=120 else 1)
    store=Store(args.db)
    try:
        while True:
            import shutil
            if shutil.disk_usage(args.db.resolve().parent).free<100*1024**2:
                print(json.dumps({'paused':'LOW_DISK','orders_enabled':False}),flush=True)
                if not args.loop: raise SystemExit(1)
                time.sleep(args.interval)
                continue
            data=collect(store)
            print(json.dumps({'observed_at':data['observed_at'],'products':{p:{'components':v['components'],'errors':v['errors'],'bot_ready':v['bot_ready']} for p,v in data['products'].items()}}),flush=True)
            if not args.loop: raise SystemExit(0 if data['all_products_ready'] and data['all_components_ready'] else 1)
            time.sleep(args.interval)
    finally: store.close()


if __name__=='__main__': main()
