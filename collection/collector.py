"""Independent research collector. Public GET requests; local SQLite writes only."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import urlopen

ASSETS = {'BTC': ('XBTUSD', ('btc', 'xbt')), 'ETH': ('ETHUSD', ('eth',)),
          'XRP': ('XRPUSD', ('xrp',)), 'SOL': ('SOLUSD', ('sol',))}
GATEWAY = 'https://gateway.polymarket.us'


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def epoch(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed.timestamp()


def get_json(url, params=None):
    """Bounded retries, timeouts and response size; preserve TLS verification."""
    if params:
        url += '?' + urlencode(params)
    for attempt in range(3):
        try:
            with urlopen(url, timeout=15) as response:
                data = response.read(4_000_001)
                if len(data) > 4_000_000:
                    raise ValueError('Oversized response')
                return json.loads(data)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def candles(payload, asset, now):
    """Normalize Kraken's USD pair, excluding its current uncommitted bar."""
    if payload.get('error'):
        raise ValueError('Kraken error')
    series = [v for k, v in payload.get('result', {}).items() if k != 'last']
    if len(series) != 1 or not isinstance(series[0], list):
        raise ValueError('Ambiguous Kraken pair')
    rows = {}
    for raw in series[0]:
        if len(raw) != 8:
            raise ValueError('Invalid Kraken candle')
        opened = float(raw[0])
        if not math.isfinite(opened) or opened % 60:
            raise ValueError('Unaligned candle')
        if opened + 60 > now:
            continue
        o, h, l, c = map(float, raw[1:5])
        volume = float(raw[6])
        if (not all(math.isfinite(v) for v in (o, h, l, c, volume))
                or min(o, h, l, c) <= 0 or volume < 0
                or h < max(o, l, c) or l > min(o, h, c)):
            raise ValueError('Invalid OHLCV')
        row = dict(asset=asset, source_name='Kraken', source_symbol=ASSETS[asset][0],
                   interval_seconds=60, candle_open=iso(opened), open_price=o,
                   high_price=h, low_price=l, close_price=c, volume=volume,
                   completed=True, is_official_settlement_feed=False)
        if opened in rows and rows[opened] != row:
            raise ValueError('Conflicting duplicate candle')
        rows[opened] = row
    return [rows[t] for t in sorted(rows)]


def unwrap(payload, key):
    root = payload.get('data', payload)
    return root.get(key, root) if isinstance(root, dict) else root


def market(get, asset, start, now):
    slug = f'{asset.lower()}-updown-15m-{datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d-%H%M}z'
    event = unwrap(get(GATEWAY + '/v1/events/slug/' + slug), 'event')
    if not isinstance(event, dict) or event.get('slug') != slug:
        raise ValueError('Event identity mismatch')
    linked = event.get('markets')
    if isinstance(linked, dict):
        linked = list(linked.values())
    if not isinstance(linked, list) or len(linked) != 1 or not isinstance(linked[0], dict):
        raise ValueError('Unique contract required')
    contract = linked[0].get('slug')
    if not isinstance(contract, str) or not contract:
        raise ValueError('Missing contract slug')
    details = unwrap(get(GATEWAY + '/v1/market/slug/' + quote(contract, safe='')), 'market')
    if not isinstance(details, dict) or details.get('slug') != contract:
        raise ValueError('Contract identity mismatch')
    terms = details.get('assetPriceTerms') or {}
    if (str((terms.get('asset') or {}).get('symbol', '')).lower() not in ASSETS[asset][1]
            or terms.get('marketType') not in ('UPDOWN', 'UP_DOWN')
            or epoch(terms.get('windowStart', '')) != start
            or epoch(terms.get('windowEnd', '')) != start + 900):
        raise ValueError('Contract terms mismatch')
    target = terms.get('priceToBeat') or {}
    value = float(target.get('value', 'nan'))
    if target.get('currency') != 'USD' or not math.isfinite(value) or value <= 0:
        raise ValueError('Official USD target unavailable')
    # Verification here is identity/terms verification, NOT settlement verification.
    return dict(market_slug=slug, asset=asset, duration_seconds=900,
                window_start=iso(start), window_end=iso(start + 900),
                contract_slug=contract, market_type=terms['marketType'],
                official_price_to_beat=value, reference_source='Polymarket US assetPriceTerms',
                settlement_status='PENDING', updated_at=iso(now)), details


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, payload TEXT, PRIMARY KEY(kind,key))')
        self.db.execute('CREATE TABLE IF NOT EXISTS evidence (market_slug TEXT, observed_at TEXT, payload TEXT, PRIMARY KEY(market_slug,observed_at))')

    def put(self, kind, rows):
        added = 0
        with self.db:
            for row in rows:
                key = row['market_slug'] if kind == 'market' else '|'.join(str(row[k]) for k in ('asset', 'source_name', 'interval_seconds', 'candle_open'))
                payload = json.dumps(row, sort_keys=True, allow_nan=False)
                old = self.db.execute('SELECT payload FROM records WHERE kind=? AND key=?', (kind, key)).fetchone()
                if old and old[0] == payload:
                    continue
                self.db.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,key) DO UPDATE SET payload=excluded.payload', (kind, key, payload))
                added += 1
        return added

    def evidence(self, slug, now, details):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?)', (slug, iso(now), json.dumps(details, allow_nan=False)))


def collect(store, get=get_json, now=None):
    now = time.time() if now is None else now
    report = {}
    for asset, (pair, _) in ASSETS.items():
        status = {}
        try:
            bars = candles(get('https://api.kraken.com/0/public/OHLC', {'pair': pair, 'interval': 1}), asset, now)
            status['candles_changed'] = store.put('candle', bars)
            status['latest_candle_age_seconds'] = now - epoch(bars[-1]['candle_open']) - 60 if bars else None
            status['stale'] = not bars or status['latest_candle_age_seconds'] > 120
            status['gap_count'] = sum(epoch(b['candle_open']) - epoch(a['candle_open']) > 60 for a, b in zip(bars, bars[1:]))
        except Exception as exc:
            status['candle_error'] = type(exc).__name__
        status['markets_changed'] = 0
        status['market_errors'] = []
        # Refresh recent closed windows as well as the live window; retain raw
        # evidence for a future independently reviewed settlement adapter.
        for start in range(int(now) // 900 * 900 - 1800, int(now) // 900 * 900 + 1, 900):
            try:
                row, details = market(get, asset, start, now)
                store.evidence(row['market_slug'], now, details)
                status['markets_changed'] += store.put('market', [row])
            except Exception as exc:
                status['market_errors'].append({'window_start': iso(start), 'error': type(exc).__name__})
        report[asset] = status
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True, help='Local SQLite path; never Supabase')
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    store = Store(args.db)
    try:
        while True:
            report = collect(store)
            print(json.dumps(report), flush=True)
            if not args.loop:
                failed = any(v.get('candle_error') or v.get('stale') or v['market_errors'] for v in report.values())
                raise SystemExit(1 if failed else 0)
            time.sleep(60)
    finally:
        store.db.close()


if __name__ == '__main__':
    main()
