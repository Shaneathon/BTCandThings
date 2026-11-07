"""Authenticated read-only paper status endpoint, loopback by default."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import sqlite3


def snapshot(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()
        result=json.loads(row[0]) if row else {'account':{'mode':'PAPER','live_orders_enabled':False},'status':'AWAITING_FIRST_CYCLE'}
    if result.get('operation_mode')=='OBSERVED_BOOK_PAPER':
        from trading_bot.display_status import enrich
        try: return enrich(path,result)
        except Exception as error: result['display_health_error']=type(error).__name__
    return result


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,ledger,token,reader=snapshot,**kwargs):
        self.ledger,self.token,self.reader=ledger,token,reader
        super().__init__(*args,**kwargs)

    def do_GET(self):
        from urllib.parse import urlsplit,parse_qs
        target=urlsplit(self.path)
        if target.path not in ('/status','/trades') or (target.path=='/status' and target.query):
            self.send_error(404)
            return
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.token):
            self.send_error(401)
            return
        try:
            if target.path=='/trades':
                from trading_bot.trade_history import page
                q=parse_qs(target.query,keep_blank_values=True)
                if set(q)-{'wallet','page','limit','as_of'} or any(len(v)!=1 for v in q.values()): raise ValueError('Invalid query')
                result=page(self.ledger,wallet=q.get('wallet',['*'])[0],number=int(q.get('page',['1'])[0]),
                            limit=int(q.get('limit',['50'])[0]),as_of=float(q['as_of'][0]) if 'as_of' in q else None)
            else: result=self.reader(self.ledger)
            payload=json.dumps(result).encode()
            if len(payload)>4_000_000: raise RuntimeError('Response exceeds byte limit')
        except ValueError:
            self.send_error(400,'Invalid request')
            return
        except LookupError:
            self.send_error(404,'History unavailable')
            return
        except Exception:
            self.send_error(503,'Status unavailable')
            return
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self,*args):
        pass  # Never log request headers or tokens.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    token=os.environ.get('PBOT_READ_TOKEN','')
    if len(token)<32:
        parser.error('Set a private PBOT_READ_TOKEN of at least 32 characters')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,ledger=args.ledger,token=token))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__=='__main__':
    main()
