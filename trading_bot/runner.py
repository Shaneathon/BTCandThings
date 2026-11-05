"""Run the PAPER engine against collected research data and reviewed quotes."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from trading_bot.core import Config, PaperBot


def inputs(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        markets=[json.loads(r[0]) for r in db.execute("SELECT payload FROM records WHERE kind='market'")]
        predictions=[json.loads(r[0]) for r in db.execute('SELECT payload FROM research_snapshots')]
    return markets,predictions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector-db',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--quotes',type=Path,required=True,help='Reviewed normalized quotes, including verified side mapping and depth')
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--kill-file',type=Path,required=True)
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args()
    if args.ledger.resolve()==args.collector_db.resolve():
        parser.error('Paper ledger must be separate from the collector database')
    config=Config(**json.loads(args.config.read_text()))
    bot=PaperBot(args.ledger,config)
    try:
        while True:
            markets,predictions=inputs(args.collector_db)
            if args.quotes.stat().st_size>4_000_000:
                raise ValueError('Quote file exceeds supported size')
            quotes=json.loads(args.quotes.read_text())
            if not isinstance(quotes,list):
                raise ValueError('Quote file must be a JSON list')
            result=bot.cycle(markets,predictions,quotes,time.time(),kill_switch=args.kill_file.exists())
            print(json.dumps(result),flush=True)
            if not args.loop:
                return
            time.sleep(5)
    finally:
        bot.close()


if __name__=='__main__':
    main()
