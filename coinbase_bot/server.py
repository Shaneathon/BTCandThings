"""Separate CBot ledger/token/port using the common read-only status transport."""
import argparse
from functools import partial
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
from trading_bot.server import Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    token=os.environ.get('CBOT_READ_TOKEN','')
    if len(token)<32: parser.error('Configure a private CBOT_READ_TOKEN of at least 32 characters')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,ledger=args.ledger,token=token))
    try: server.serve_forever()
    finally: server.server_close()


if __name__=='__main__': main()
