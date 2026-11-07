"""Read-only public market execution audit. Never submits orders or assumes fills."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

GATEWAY = 'https://gateway.polymarket.us'


def epoch(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timezone required')
    return stamp.timestamp()


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean amount')
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed < 0:
        raise ValueError('Invalid amount')
    return parsed


def book_summary(payload, contract, received_at):
    """Prices/quantities only. LONG is not silently interpreted as UP."""
    book = payload.get('marketData') if isinstance(payload, dict) else None
    if not isinstance(book, dict) or book.get('marketSlug') != contract:
        raise ValueError('BOOK_CONTRACT_MISMATCH')
    if book.get('state') != 'MARKET_STATE_OPEN':
        raise ValueError('BOOK_NOT_OPEN')
    sides = {}
    for source, target, reverse in [('bids', 'long_bids', True), ('offers', 'long_offers', False)]:
        levels = book.get(source)
        if not isinstance(levels, list) or not levels:
            raise ValueError('EMPTY_BOOK_SIDE')
        combined = {}
        for level in levels:
            price = level['px']
            if price.get('currency') != 'USD':
                raise ValueError('BOOK_CURRENCY')
            px, qty = number(price['value']), number(level['qty'])
            if not 0 < px < 1 or qty <= 0:
                raise ValueError('BOOK_PRICE_OR_SIZE')
            # Duplicate price rows may represent overlapping aggregates. Refuse
            # to double count them as additional executable liquidity.
            if px in combined:
                raise ValueError('DUPLICATE_PRICE_LEVEL')
            combined[px] = qty
        sides[target] = [{'price': str(px), 'quantity': str(combined[px])}
                         for px in sorted(combined, reverse=reverse)[:3]]
    if number(sides['long_bids'][0]['price']) >= number(sides['long_offers'][0]['price']):
        raise ValueError('LOCKED_OR_CROSSED_BOOK')
    stamp = book.get('transactTime')
    age = received_at - epoch(stamp) if stamp else None
    return dict(**sides, exchange_timestamp=stamp, exchange_age_seconds=age,
                timestamp_fresh=age is not None and 0 <= age <= 15,
                side_mapping_verified=False, fees_verified=False,
                tradable_quote_approved=False)


def get_json(url):
    request = Request(url, headers={'User-Agent': 'Shaneathon-ExecutionAudit/1.0'}, method='GET')
    with urlopen(request, timeout=10) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('RESPONSE_TOO_LARGE')
    return json.loads(raw)


def write_private(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.execution-audit-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def inspect_market(market, get, now):
    contract = market['contract_slug']
    details = get(GATEWAY + '/v1/market/slug/' + quote(contract, safe=''))
    if not isinstance(details, dict):
        raise ValueError('METADATA_RESPONSE_INVALID')
    details = details.get('data', details)
    if not isinstance(details, dict):
        raise ValueError('METADATA_RESPONSE_INVALID')
    details = details.get('market', details)
    if not isinstance(details, dict) or details.get('slug') != contract:
        raise ValueError('METADATA_CONTRACT_MISMATCH')
    terms = details.get('assetPriceTerms') or {}
    symbols = {'BTC': {'btc', 'xbt'}, 'ETH': {'eth'}, 'XRP': {'xrp'}, 'SOL': {'sol'},
               'GOLD': {'gold', 'xau'}, 'SILVER': {'silver', 'xag'}}
    if (str((terms.get('asset') or {}).get('symbol', '')).lower() not in symbols.get(market['asset'], set())
            or terms.get('marketType') != 'ASSET_PRICE_MARKET_TYPE_UP_DOWN'
            or epoch(terms['windowStart']) != epoch(market['window_start'])
            or epoch(terms['windowEnd']) != epoch(market['window_end'])
            or (terms.get('priceToBeat') or {}).get('currency') != 'USD'
            or number(terms['priceToBeat']['value']) != number(market['official_price_to_beat'])):
        raise ValueError('CONTRACT_TERMS_MISMATCH')
    raw_book = get(GATEWAY + '/v1/markets/' + quote(contract, safe='') + '/book')
    received = now()
    if not epoch(market['window_start']) <= received < epoch(market['window_end']):
        raise ValueError('WINDOW_ROLLED_DURING_AUDIT')
    summary = book_summary(raw_book, contract, received)
    summary.update(received_at=received, market_slug=market['market_slug'], contract_slug=contract,
                   description=details.get('description'), market_sides=details.get('marketSides'),
                   fee_coefficient=details.get('feeCoefficient'),
                   order_price_tick=details.get('orderPriceMinTickSize'),
                   minimum_trade_quantity=details.get('minimumTradeQty'))
    return summary, dict(metadata=details, book=raw_book)


def retry_time(error, now):
    from email.utils import parsedate_to_datetime
    raw = (getattr(error, 'headers', None) or {}).get('Retry-After')
    try:
        delay = float(raw)
        if math.isfinite(delay) and delay >= 0:
            return now + max(60, delay)
    except (TypeError, ValueError):
        pass
    try:
        stamp = parsedate_to_datetime(raw)
        if stamp.tzinfo is not None:
            return max(now + 60, stamp.timestamp())
    except (TypeError, ValueError, OverflowError):
        pass
    return now + 60


def audit(source, output, get=get_json, now=time.time, pause=time.sleep):
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError('Audit destination must not be a symlink')
    report = dict(observed_at=now(), mode='PUBLIC_EXECUTION_AUDIT', real_trading=False,
                  simulated_orders_submitted=0, markets=[], note='Read-only evidence; no paper fill is approved by this audit.')
    budget = output / 'request-budget.json'
    if budget.exists():
        retry = json.loads(budget.read_text()).get('retry_after', 0)
        if retry > now():
            report.update(state='RATE_LIMIT_COOLDOWN', retry_after=retry)
            write_private(output / 'latest.json', report)
            return report
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('BEGIN')
        markets = [json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind='market'")]
    active = [m for m in markets if epoch(m['window_start']) <= now() < epoch(m['window_end'])]
    # Prioritize the original BTC control comparison, then the other markets.
    active.sort(key=lambda m: (m.get('asset') != 'BTC', m.get('duration_seconds') != 900, m['market_slug']))
    unique = {}
    for market in active:
        unique.setdefault((market['asset'], market['duration_seconds']), market)
    for market in list(unique.values())[:10]:
        label = market['asset'] + '_' + str(market['duration_seconds'] // 60) + 'm'
        print('Checking', label, flush=True)
        result = dict(stream=label, market_slug=market['market_slug'])
        try:
            summary, raw = inspect_market(market, get, now)
            result.update(state='BOOK_OBSERVED_NOT_APPROVED', **summary)
            write_private(output / (label + '.json'), raw)
        except HTTPError as error:
            result.update(state='HTTP_ERROR', http_status=error.code)
            if error.code == 429:
                retry = retry_time(error, now())
                write_private(budget, dict(retry_after=retry))
                result['retry_after'] = retry
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
            result.update(state='UNVERIFIED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)
        report['markets'].append(result)
        write_private(output / 'latest.json', report)
        if result.get('http_status') == 429:
            break
        pause(2)
    report['state'] = ('PARTIAL_RATE_LIMIT' if any(r.get('http_status') == 429 for r in report['markets'])
                       else 'AUDIT_COMPLETE' if unique else 'NO_CURRENT_COLLECTOR_MARKETS')
    report['remaining_requirements'] = [
        'Review exact contract UP/DOWN to LONG/SHORT mapping; Yes/No labels alone are not approval.',
        'Confirm book quantity units, freshness and short-side price conversion.',
        'Verify actual fee formula and tick/minimum sizes; feeCoefficient alone is not a fee formula.',
        'Use one shared decision/order specification for paper and any future live adapter.',
        'Start a separate forward ledger with latency, depth-limited fills, costs and recorded skip reasons.'
    ]
    write_private(output / 'latest.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source, args.output)
    # Public market evidence only; never reads credentials or prints environment.
    print(json.dumps(report, indent=2, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
