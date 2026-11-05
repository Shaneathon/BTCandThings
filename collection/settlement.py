"""Conservative official settlement reconciliation. Never use proxy winners."""
import json
from urllib.parse import quote
from collector import epoch, iso, unwrap

FINAL = {'SETTLED', 'RESOLVED', 'MARKET_STATE_SETTLED', 'MARKET_STATE_RESOLVED'}


def winner(details):
    """Recognize explicit semantic UP/DOWN only; numeric sides stay pending.

These fields match the incumbent app's explicit-winner path. Live compatibility
still needs verification; missing/unknown schemas are not guessed.
"""
    states = [str(details[k]).upper() for k in ('state', 'status') if details.get(k) is not None]
    if not states or any(s not in FINAL for s in states):
        return None
    values = [details[k] for k in ('winningOutcome', 'winningSide') if details.get(k) is not None]
    if not values or any(not isinstance(v, str) or v.upper() not in ('UP', 'DOWN') for v in values):
        return None
    values = {v.upper() for v in values}
    return next(iter(values)) if len(values) == 1 else None


def reconcile(store, get, now, limit=20):
    from ten_streams import GATEWAY, verified_target
    store.db.execute('''CREATE TABLE IF NOT EXISTS settlement_checks (
        market_slug TEXT PRIMARY KEY, checked_at REAL NOT NULL)''')
    # Oldest-last-checked rotation includes old pending windows; failed queries
    # don't starve the queue. Retry at most once per five minutes per market.
    rows = store.db.execute('''SELECT r.key,r.payload FROM records r
        LEFT JOIN settlement_checks c ON c.market_slug=r.key
        WHERE r.kind='market' AND (c.checked_at IS NULL OR c.checked_at<=?)
        ORDER BY COALESCE(c.checked_at,0),r.key''', (now-300,)).fetchall()
    report = dict(verified=0, pending=0, errors=0, checked=0)
    for slug, payload in rows:
        row = json.loads(payload)
        if row['settlement_status'] != 'PENDING' or epoch(row['window_end']) > now:
            continue
        if report['checked'] >= limit:
            break
        report['checked'] += 1
        with store.db:
            store.db.execute('INSERT INTO settlement_checks VALUES (?,?) ON CONFLICT(market_slug) DO UPDATE SET checked_at=excluded.checked_at', (slug,now))
        try:
            details = unwrap(get(GATEWAY+'/v1/market/slug/'+quote(row['contract_slug'],safe='')), 'market')
            if not isinstance(details, dict) or details.get('slug') != row['contract_slug']:
                raise ValueError('Settlement contract mismatch')
            target = verified_target(details,row['asset'],int(epoch(row['window_start'])),
                                     '5m' if row['duration_seconds']==300 else '15m')
            if target is None or target != row['official_price_to_beat']:
                raise ValueError('Settlement terms changed or unverified')
            store.evidence(slug,now,details)
            result = winner(details)
            if result is None:
                report['pending'] += 1
                continue
            row.update(settlement_status='VERIFIED', official_winner=result, settled_at=iso(now),updated_at=iso(now),
                       settlement_evidence=json.dumps(dict(source=GATEWAY+'/v1/market/slug/'+quote(row['contract_slug'],safe=''),
                                                           observed_at=iso(now), contract=details),sort_keys=True,allow_nan=False))
            store.put('market',[row])
            report['verified'] += 1
        except Exception:
            report['errors'] += 1
    return report
