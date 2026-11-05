"""Coin tracker authenticated read-only status; no bot/account/trade endpoints."""
import argparse
from functools import partial
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
from trading_bot.server import Handler
from coinbase_tracker.collector import snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args()
    token=os.environ.get('COIN_READ_TOKEN','')
    if len(token)<32: parser.error('Configure a private COIN_READ_TOKEN of at least 32 characters')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,ledger=args.db,token=token,reader=snapshot))
    try: server.serve_forever()
    finally: server.server_close()


if __name__=='__main__': main()
