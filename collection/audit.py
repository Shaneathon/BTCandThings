"""Read-only local collector audit and deterministic schema-shaped JSON export.

No network calls or production database connections. Exit 1 on unhealthy data.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import time

from collector import ASSETS, epoch

TABLES = {'candle': 'asset_proxy_candles', 'market': 'asset_market_windows'}


def finite(value, positive=False):
    number = float(value)
    if isinstance(value, bool) or not math.isfinite(number) or (positive and number <= 0):
        raise ValueError('Invalid numeric value')
    return number


def validate(kind, row, now):
    if row['asset'] not in ASSETS:
        raise ValueError('Unsupported asset')
    if kind == 'candle':
        if (row['source_name'] != 'Kraken' or row['source_symbol'] != ASSETS[row['asset']][0]
                or row['interval_seconds'] != 60 or row['completed'] is not True
                or row['is_official_settlement_feed'] is not False):
            raise ValueError('Invalid candle provenance')
        opened = epoch(row['candle_open'])
        if opened % 60 or opened + 60 > now:
            raise ValueError('Incomplete or unaligned candle')
        o, h, l, c = [finite(row[k], True) for k in ('open_price', 'high_price', 'low_price', 'close_price')]
        if h < max(o, l, c) or l > min(o, h, c) or finite(row['volume']) < 0:
            raise ValueError('Invalid OHLCV')
    elif kind == 'market':
        start, end = epoch(row['window_start']), epoch(row['window_end'])
        if start % 900 or row['duration_seconds'] != 900 or end != start + 900:
            raise ValueError('Invalid market window')
        if not row['contract_slug'] or row['market_type'] not in ('UP_DOWN', 'UPDOWN'):
            raise ValueError('Missing verified identity')
        from datetime import datetime, timezone
        expected = f"{row['asset'].lower()}-updown-15m-{datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d-%H%M}z"
        if row['market_slug'] != expected:
            raise ValueError('Market slug mismatch')
        finite(row['official_price_to_beat'], True)
        # This collector has no reviewed settlement adapter. Never export a
        # VERIFIED outcome from a manual edit or an untrusted local record.
        if row['settlement_status'] != 'PENDING' or row.get('official_winner') is not None:
            raise ValueError('Unsupported settlement claim')
        if row['reference_source'] != 'Polymarket US assetPriceTerms' or epoch(row['updated_at']) > now:
            raise ValueError('Invalid market provenance')
    else:
        raise ValueError('Unknown record kind')


def audit(path, now=None):
    now = time.time() if now is None else now
    result = {'healthy': False, 'errors': [], 'assets': {},
              'tables': {name: [] for name in TABLES.values()}}
    # mode=ro prevents accidental creation, writes, or schema initialization.
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        records = connection.execute('SELECT kind,key,payload FROM records ORDER BY kind,key').fetchall()
        for kind, key, payload in records:
            try:
                row = json.loads(payload)
                validate(kind, row, now)
                expected = row['market_slug'] if kind == 'market' else '|'.join(str(row[k]) for k in ('asset', 'source_name', 'interval_seconds', 'candle_open'))
                if key != expected:
                    raise ValueError('Storage key mismatch')
                result['tables'][TABLES[kind]].append(row)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                # Do not echo raw records or provider response bodies.
                result['errors'].append({'kind': kind, 'error': type(exc).__name__})
        for asset in ASSETS:
            bars = sorted((r for r in result['tables']['asset_proxy_candles'] if r['asset'] == asset), key=lambda r: epoch(r['candle_open']))
            windows = [r for r in result['tables']['asset_market_windows'] if r['asset'] == asset]
            missing = sum(max(0, int((epoch(b['candle_open'])-epoch(a['candle_open']))/60)-1) for a, b in zip(bars, bars[1:]))
            age = now - epoch(bars[-1]['candle_open']) - 60 if bars else None
            current = any(epoch(r['window_start']) <= now < epoch(r['window_end']) for r in windows)
            result['assets'][asset] = dict(candles=len(bars), markets=len(windows), missing_minutes=missing,
                                         latest_candle_age_seconds=age, stale=age is None or age > 120,
                                         current_market_verified=current)
        result['healthy'] = not result['errors'] and all(not r['stale'] and not r['missing_minutes'] and r['current_market_verified'] for r in result['assets'].values())
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='New JSON file; existing files are never overwritten')
    args = parser.parse_args()
    result = audit(args.db)
    if args.out:
        # Reject invalid records as a complete batch, rather than silently
        # preparing a partial upload. Health warnings remain visible in exports.
        if result['errors']:
            print(json.dumps({k: v for k, v in result.items() if k != 'tables'}))
            raise SystemExit(1)
        with args.out.open('x') as stream:
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'tables'}, sort_keys=True))
    raise SystemExit(0 if result['healthy'] else 1)


if __name__ == '__main__':
    main()
