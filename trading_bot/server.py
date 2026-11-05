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
        return json.loads(row[0]) if row else {'account':{'mode':'PAPER','live_orders_enabled':False},'status':'AWAITING_FIRST_CYCLE'}


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,ledger,token,reader=snapshot,**kwargs):
        self.ledger,self.token,self.reader=ledger,token,reader
        super().__init__(*args,**kwargs)

    def do_GET(self):
        if self.path!='/status':
            self.send_error(404)
            return
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.token):
            self.send_error(401)
            return
        try:
            payload=json.dumps(self.reader(self.ledger)).encode()
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
