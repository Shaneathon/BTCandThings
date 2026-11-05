"""Research-only Kraken 1-minute OHLC collector for BTC, ETH, XRP and SOL.

Writes a local SQLite database; never sends orders or touches existing BTC tables.
Run: python3 scripts/collect_four_crypto.py --db research_candles.sqlite
Use --once for a single snapshot. The newest (possibly incomplete) candle is excluded.
"""
import argparse
import json
import logging
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD", "XRP": "XRPUSD", "SOL": "SOLUSD"}
API = "https://api.kraken.com/0/public/OHLC"
LOG = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS crypto_proxy_candles (
    asset TEXT NOT NULL,
    source TEXT NOT NULL,
    source_pair TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL,
    candle_open_utc TEXT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    vwap REAL NOT NULL,
    volume REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    collected_at_utc TEXT NOT NULL,
    PRIMARY KEY(asset, source, interval_seconds, candle_open_utc)
);
"""

def utc(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat()

def fetch(pair):
    url = API + "?" + urllib.parse.urlencode({"pair": pair, "interval": 1})
    req = urllib.request.Request(url, headers={"User-Agent": "BTCandThings-research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if payload.get("error"):
        raise RuntimeError(f"Kraken returned errors for {pair}: {payload['error']}")
    result = payload["result"]
    keys = [k for k in result if k != "last"]
    if len(keys) != 1:
        raise ValueError(f"Unexpected Kraken OHLC response keys: {keys}")
    return result[keys[0]]

def collect(db):
    now = int(time.time())
    total = 0
    for asset, pair in PAIRS.items():
        try:
            candles = fetch(pair)
            rows = []
            for candle in candles[:-1]:
                start = int(candle[0])
                # Kraken's last OHLC row is the uncommitted candle.
                # Also guard against any candle not yet complete by wall clock.
                if start + 60 > now:
                    continue
                o, h, l, c, vwap, vol = map(float, candle[1:7])
                count = int(candle[7])
                if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
                    raise ValueError(f"Invalid OHLC values for {asset} at {start}")
                rows.append((asset, "Kraken", pair, 60, utc(start),
                             o, h, l, c, vwap, vol, count, utc(now)))
            with db:
                db.executemany("""
                    INSERT OR IGNORE INTO crypto_proxy_candles
                    (asset, source, source_pair, interval_seconds, candle_open_utc,
                     open_price, high_price, low_price, close_price, vwap,
                     volume, trade_count, collected_at_utc)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, rows)
            total += len(rows)
            LOG.info("%s: checked %d completed 1m candles", asset, len(rows))
        except Exception:
            LOG.exception("%s: collection failed; other assets will continue", asset)
        time.sleep(1)
    return total

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="research_candles.sqlite")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(SCHEMA)
        while True:
            collect(db)
            if args.once:
                break
            time.sleep(args.interval)

if __name__ == "__main__":
    main()
