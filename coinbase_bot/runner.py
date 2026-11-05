"""Coinbase PAPER loop. Public reads only, no Coinbase credentials or orders."""
import argparse
import json
from pathlib import Path
import time
from coinbase_bot.core import Config,PaperBot
from coinbase_bot.market_data import fetch_all


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--kill-file',type=Path,required=True)
    parser.add_argument('--snapshots',type=Path,help='Offline reviewed fixture data instead of public reads')
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args()
    bot=PaperBot(args.ledger,Config(**json.loads(args.config.read_text())))
    try:
        while True:
            if args.snapshots:
                if args.snapshots.stat().st_size>4_000_000: raise ValueError('Snapshot file too large')
                data=json.loads(args.snapshots.read_text())
            else:
                data=fetch_all()
            report=bot.cycle(data,time.time(),kill_switch=args.kill_file.exists())
            print(json.dumps(report),flush=True)
            if not args.loop: return
            time.sleep(60)
    finally:
        bot.close()


if __name__=='__main__': main()
