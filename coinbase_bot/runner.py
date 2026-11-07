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
    parser.add_argument('--tracker-url',help='Optional coin tracker /status source instead of duplicate public requests')
    parser.add_argument('--observed',action='store_true',help='Separate delayed limit-order execution ledger')
    args=parser.parse_args()
    if args.snapshots and args.tracker_url:
        parser.error('Choose tracker or offline snapshots, not both')
    if args.observed:
        from coinbase_bot.observed import ObservedBot,ObservedConfig
        bot=ObservedBot(args.ledger,ObservedConfig(**json.loads(args.config.read_text())))
    else:
        bot=PaperBot(args.ledger,Config(**json.loads(args.config.read_text())))
    try:
        while True:
            try:
                if args.tracker_url:
                    import os
                    from coinbase_tracker.client import fetch,bot_inputs
                    data=bot_inputs(fetch(args.tracker_url,os.environ.get('COIN_READ_TOKEN','')))
                elif args.snapshots:
                    if args.snapshots.stat().st_size>4_000_000: raise ValueError('Snapshot file too large')
                    data=json.loads(args.snapshots.read_text())
                else:
                    data=fetch_all()
            except (OSError,ValueError,TypeError,KeyError):
                if not args.observed: raise
                data={}  # Keep journaling/expiring proposals without fabricated fills.
            report=bot.cycle(data,time.time(),kill_switch=args.kill_file.exists())
            print(json.dumps(report),flush=True)
            if not args.loop: return
            time.sleep(5 if args.observed else 60)
    finally:
        bot.close()


if __name__=='__main__': main()
