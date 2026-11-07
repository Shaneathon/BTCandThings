"""Sample public XAU/XAG USD quotes and expose completed observed 1m bars.

No synthetic backfill, trades, credentials or futures substitutions. A candle
describes sampled quotes, not complete exchange-traded OHLC or official index.
"""
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
from pathlib import Path
import signal
import sqlite3
import threading
import time
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request,urlopen

SYMBOLS={'GOLD':'XAU','SILVER':'XAG'}


def validate(payload,asset,now):
    if payload.get('symbol')!=SYMBOLS[asset] or payload.get('currency')!='USD':
        raise ValueError('Wrong quote instrument/currency')
    if isinstance(payload.get('price'),bool): raise ValueError('Invalid quote price')
    price=float(payload['price'])
    when=datetime.fromisoformat(payload['updatedAt'].replace('Z','+00:00'))
    if when.tzinfo is None: raise ValueError('Quote time must include timezone')
    source=when.timestamp()
    if not math.isfinite(price) or price<=0 or not 0<=now-source<=120:
        raise ValueError('Stale/future quote or invalid price')
    if float(payload.get('exchangeRate',1))!=1: raise ValueError('Unexpected converted quote')
    return source,price


class Store:
    def __init__(self,path):
        self.path=Path(path)
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS quotes (
            asset TEXT,source_at REAL,received_at REAL,price REAL,payload TEXT,PRIMARY KEY(asset,source_at));
            CREATE TABLE IF NOT EXISTS feed_status (asset TEXT PRIMARY KEY,payload TEXT);
            CREATE TABLE IF NOT EXISTS cooldowns (asset TEXT PRIMARY KEY,retry_until REAL);''')

    def put(self,asset,payload,now):
        source,price=validate(payload,asset,now)
        encoded=json.dumps(payload,allow_nan=False)
        with self.db:
            old=self.db.execute('SELECT price FROM quotes WHERE asset=? AND source_at=?',(asset,source)).fetchone()
            if old and old[0]!=price: raise ValueError('Conflicting quote for the same source timestamp')
            self.db.execute('INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?)',(asset,source,now,price,encoded))

    def status(self,asset,data):
        with self.db:
            self.db.execute('INSERT INTO feed_status VALUES (?,?) ON CONFLICT(asset) DO UPDATE SET payload=excluded.payload',
                            (asset,json.dumps(data,allow_nan=False)))

    def candles(self,asset,now):
        with sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute('SELECT source_at,price FROM quotes WHERE asset=? AND source_at>=? ORDER BY source_at',
                            (asset,now-4*3600)).fetchall()
            status=db.execute('SELECT payload FROM feed_status WHERE asset=?',(asset,)).fetchone()
        grouped={}
        for source,price in rows: grouped.setdefault(int(source)//60*60,[]).append((source,price))
        candles=[]
        for start,points in sorted(grouped.items()):
            # At least two actual source updates spanning half of the minute.
            if start+60>now or len(points)<2 or points[-1][0]-points[0][0]<30:
                continue
            prices=[p for _,p in points]
            candles.append(dict(time=start,open=prices[0],high=max(prices),low=min(prices),close=prices[-1],
                                volume=None,sample_count=len(points),first_source_at=points[0][0],last_source_at=points[-1][0]))
        # Keep only a contiguous suffix; never fill a missing minute.
        suffix=[]
        for bar in reversed(candles):
            if suffix and suffix[-1]['time']-bar['time']!=60: break
            suffix.append(bar)
            if len(suffix)==120: break
        suffix.reverse()
        return dict(asset=asset,currency='USD',source_symbol=SYMBOLS[asset]+'/USD',
                    source_name='Gold-API sampled spot proxy',is_official_settlement_feed=False,
                    candle_kind='SAMPLED_QUOTE_OHLC_NOT_COMPLETE_MARKET_CANDLES',candles=suffix,
                    completed_candles=len(suffix),minimum_research_candles=50,
                    feed_status=json.loads(status[0]) if status else {'state':'WARMING_UP'})

    def close(self): self.db.close()


def get_quote(asset):
    req=Request('https://api.gold-api.com/price/'+SYMBOLS[asset],headers={'User-Agent':'Shaneathon-MetalsResearch/1.0'})
    with urlopen(req,timeout=10) as response: return json.loads(response.read(100000))


def retry_time(error,now):
    from email.utils import parsedate_to_datetime
    raw=(getattr(error,'headers',None) or {}).get('Retry-After')
    if raw:
        try: return now+max(60,min(86400,int(raw)))
        except (ValueError,TypeError):
            try: return max(now+60,parsedate_to_datetime(raw).timestamp())
            except (ValueError,TypeError,OverflowError): pass
    return now+900


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed=urlsplit(self.path);asset=parse_qs(parsed.query).get('asset',[''])[0]
            if parsed.path!='/candles' or asset not in SYMBOLS:
                self.send_error(404);return
            try: data=store.candles(asset,time.time())
            except Exception: self.send_error(503);return
            encoded=json.dumps(data,allow_nan=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(encoded)))
            self.end_headers();self.wfile.write(encoded)
        def log_message(self,*args): pass
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    store=Store(args.db)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(store))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def stop(signum,frame): raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    try:
        while True:
            started=time.monotonic()
            for asset in SYMBOLS:
                now=time.time()
                retry=store.db.execute('SELECT retry_until FROM cooldowns WHERE asset=?',(asset,)).fetchone()
                if retry and retry[0]>now:
                    store.status(asset,dict(state='RATE_LIMIT_COOLDOWN',retry_after=retry[0],observed_at=now));continue
                try:
                    quote=get_quote(asset);observed=time.time()
                    store.put(asset,quote,observed)
                    count=store.candles(asset,observed)['completed_candles']
                    store.status(asset,dict(state='READY' if count>=50 else 'WARMING_UP',completed_candles=count,
                                           source_updated_at=quote['updatedAt'],observed_at=observed))
                except Exception as error:
                    status=dict(state='UNAVAILABLE',error=type(error).__name__,http_status=getattr(error,'code',None),observed_at=time.time())
                    if getattr(error,'code',None)==429:
                        retry=retry_time(error,time.time())
                        with store.db:
                            store.db.execute('INSERT INTO cooldowns VALUES (?,?) ON CONFLICT(asset) DO UPDATE SET retry_until=excluded.retry_until',(asset,retry))
                        status.update(state='RATE_LIMIT_COOLDOWN',retry_after=retry)
                    store.status(asset,status)
            time.sleep(max(1,20-(time.monotonic()-started)))
    finally:
        server.shutdown();server.server_close();thread.join();store.close()


if __name__=='__main__': main()
