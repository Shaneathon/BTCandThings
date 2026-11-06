"""Ten-stream shadow collector. Public reads, local SQLite only; never trades."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload'))
from market_workspace import ASSETS, LISTED_DURATIONS, DURATIONS, event_slug, verified_target
from market_candles import load_candles
from tracker_panels import research_signal
from collector import Store, get_json, unwrap, iso, epoch

STREAMS = [(asset, duration) for asset in ASSETS for duration in LISTED_DURATIONS[asset]]
GATEWAY = 'https://gateway.polymarket.us'
MODEL = 'Multi-asset spot baseline research V1'


def market(get, asset, duration, start, now):
    slug = event_slug(asset, duration, start)
    event = unwrap(get(GATEWAY+'/v1/events/slug/'+slug), 'event')
    if not isinstance(event, dict) or event.get('slug') != slug:
        raise ValueError('Event identity mismatch')
    linked = event.get('markets')
    if isinstance(linked, dict):
        linked = list(linked.values())
    if not isinstance(linked, list) or len(linked) != 1 or not isinstance(linked[0], dict):
        raise ValueError('Unique linked contract required')
    contract = linked[0].get('slug')
    if not isinstance(contract, str) or not contract:
        raise ValueError('Missing contract slug')
    details = unwrap(get(GATEWAY+'/v1/market/slug/'+quote(contract, safe='')), 'market')
    if not isinstance(details, dict) or details.get('slug') != contract:
        raise ValueError('Contract identity mismatch')
    target = verified_target(details, asset, start, duration)
    if target is None:
        raise ValueError('Asset, window or official target unverified')
    return dict(market_slug=slug, asset=asset, duration_seconds=DURATIONS[duration],
                window_start=iso(start), window_end=iso(start+DURATIONS[duration]),
                contract_slug=contract, market_type=details['assetPriceTerms']['marketType'],
                official_price_to_beat=target, reference_source='Polymarket US assetPriceTerms',
                settlement_status='PENDING', updated_at=iso(now)), details


def cooldown_until(error, observed):
    from email.utils import parsedate_to_datetime
    raw = (error.headers or {}).get('Retry-After')
    if raw:
        try:
            return min(observed+max(0,int(raw)),253402300799)
        except (ValueError,TypeError,OverflowError):
            try:
                stamp=parsedate_to_datetime(raw)
                if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
                return max(observed,stamp.timestamp())
            except (ValueError,TypeError,OverflowError):
                pass
    return observed+900


def initialize(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS research_snapshots (
        market_slug TEXT, recorded_at TEXT, model_version TEXT, payload TEXT,
        PRIMARY KEY(market_slug, recorded_at, model_version))''')
    store.db.execute('''CREATE TABLE IF NOT EXISTS raw_quotes (
        market_slug TEXT, captured_at TEXT, payload TEXT, PRIMARY KEY(market_slug,captured_at))''')
    store.db.execute('''CREATE TABLE IF NOT EXISTS collector_status (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), observed_at REAL, payload TEXT)''')
    store.db.execute('CREATE TABLE IF NOT EXISTS feed_cooldowns (asset TEXT PRIMARY KEY,retry_until REAL,http_status INTEGER)')
    previous=store.db.execute('SELECT payload FROM collector_status WHERE singleton=1').fetchone()
    if previous:
        old=json.loads(previous[0])
        for asset,state in old.get('assets',{}).items():
            if state.get('http_status')==429:
                store.db.execute('INSERT OR IGNORE INTO feed_cooldowns VALUES (?,?,429)',(asset,epoch(old['observed_at'])+900))
    store.db.commit()


def collect(store, get=get_json, now=None):
    fixed_time = now is not None
    now = time.time() if now is None else now
    initialize(store)
    report = dict(observed_at=iso(now), streams={}, assets={}, settlement_adapter='NOT_CONNECTED',
                  cloud_storage='NOT_CONNECTED', real_trading=False)
    feeds = {}
    # Fetch six feeds, not ten: both crypto durations share one asset's bars.
    for asset, config in ASSETS.items():
        feed_observed = now if fixed_time else time.time()
        cooldown=store.db.execute('SELECT retry_until,http_status FROM feed_cooldowns WHERE asset=?',(asset,)).fetchone()
        if cooldown and cooldown[0]>feed_observed:
            report['assets'][asset]={'feed_error':'RATE_LIMIT_COOLDOWN','http_status':cooldown[1],'retry_after':iso(cooldown[0])}
            continue
        try:
            feed_observed = now if fixed_time else time.time()
            frame, source = load_candles(get, asset, config['pair'], feed_observed)
            feeds[asset] = frame
            rows = []
            for bar in frame.itertuples(index=False):
                rows.append(dict(asset=asset, source_name='Kraken' if config['pair'] else 'Yahoo futures proxy',
                    source_symbol=config['pair'] or {'GOLD':'GC=F','SILVER':'SI=F'}[asset], interval_seconds=60,
                    candle_open=bar.time.isoformat(), open_price=float(bar.open), high_price=float(bar.high),
                    low_price=float(bar.low), close_price=float(bar.close),
                    volume=float(bar.volume) if bar.volume == bar.volume else None,
                    completed=True, is_official_settlement_feed=False))
            report['assets'][asset] = dict(candles_changed=store.put('candle', rows), source=source)
        except Exception as exc:
            report['assets'][asset] = {'feed_error': type(exc).__name__}
            if getattr(exc, 'code', None) is not None:
                report['assets'][asset]['http_status'] = exc.code
                if exc.code==429:
                    retry=cooldown_until(exc,now if fixed_time else time.time())
                    with store.db:
                        store.db.execute('INSERT INTO feed_cooldowns VALUES (?,?,429) ON CONFLICT(asset) DO UPDATE SET retry_until=excluded.retry_until,http_status=excluded.http_status',(asset,retry))
                    report['assets'][asset]['retry_after']=iso(retry)
    for asset, duration in STREAMS:
        key = asset+'_'+duration
        seconds = DURATIONS[duration]
        stream_observed = now if fixed_time else time.time()
        start = int(stream_observed)//seconds*seconds
        state = dict(collection_ready=False, predictions_saved=0, market_errors=[], window_end=iso(start+seconds))
        report['streams'][key] = state
        # Revisit recent closed contracts and archive their raw evidence. No
        # official outcome is inferred until a finality/side adapter is reviewed.
        current = None
        for boundary in (start, start-seconds):
            try:
                row, details = market(get, asset, duration, boundary, stream_observed)
                store.evidence(row['market_slug'], stream_observed, details)
                prior = store.db.execute("SELECT payload FROM records WHERE kind='market' AND key=?", (row['market_slug'],)).fetchone()
                if prior:
                    existing = json.loads(prior[0])
                    if existing.get('settlement_status') == 'VERIFIED':
                        row = existing
                store.put('market', [row])
                if boundary == start:
                    current = row
            except Exception as exc:
                state['market_errors'].append({'window_start':iso(boundary), 'error':type(exc).__name__})
        observed = now if fixed_time else time.time()
        # A boundary can pass during HTTP I/O. Refresh the exact current
        # contract once; never re-label an old target with a new window.
        if not fixed_time and observed >= start+seconds:
            start = int(observed)//seconds*seconds
            state['window_end'] = iso(start+seconds)
            current = None
            try:
                row, details = market(get, asset, duration, start, observed)
                store.evidence(row['market_slug'], observed, details)
                store.put('market', [row])
                current = row
            except Exception as exc:
                state['market_errors'].append({'window_start':iso(start), 'error':type(exc).__name__})
            observed = time.time()
        state['metadata_ready'] = current is not None and observed < start+seconds
        # Preserve quote observations even when the spot/futures feed is down.
        if current is not None and observed < start+seconds:
            from quotes import capture
            try:
                capture(store, get, current, now if fixed_time else None)
                state['quote_status'] = 'RAW_BBO_SAVED_SIDE_MAPPING_PENDING'
            except Exception as exc:
                state['quote_status'] = 'ERROR_' + type(exc).__name__
                if getattr(exc,'code',None) is not None: state['quote_http_status']=exc.code
        if asset not in feeds:
            state['paused_reason'] = 'Asset feed unavailable'
            continue
        observed = now if fixed_time else time.time()
        signal = research_signal(feeds[asset], observed, start+seconds,
                                 current['official_price_to_beat'] if current else None)
        if not current or not signal['ready']:
            state['paused_reason'] = signal.get('reason') or 'Current official target unverified'
            continue
        state['collection_ready'] = True
        snapshot = dict(market_slug=current['market_slug'], recorded_at=iso(observed), model_version=MODEL,
                        model_role='RESEARCH', predicted_up_probability=signal['probability'],
                        lean_direction=signal['direction'], source_timestamp=iso(signal['source_time']),
                        feature_snapshot=dict(asset=asset, duration_seconds=seconds, score=signal['score'],
                                              swing=signal['swing'], spot=signal['price'], target=current['official_price_to_beat']))
        with store.db:
            cursor = store.db.execute('INSERT OR IGNORE INTO research_snapshots VALUES (?,?,?,?)',
                (snapshot['market_slug'], snapshot['recorded_at'], MODEL, json.dumps(snapshot, allow_nan=False)))
            state['predictions_saved'] = cursor.rowcount
    report['recording_ready'] = all(s.get('metadata_ready',False) for s in report['streams'].values())
    report['coverage_mode'] = 'ALL_FEEDS' if all(r['collection_ready'] for r in report['streams'].values()) else 'AVAILABLE_DATA_WITH_REPORTED_GAPS'
    report['collection_ready'] = all(r['collection_ready'] for r in report['streams'].values())
    from settlement import reconcile
    report['settlements'] = reconcile(store, get, now if fixed_time else time.time())
    report['settlement_adapter'] = 'EXPLICIT_SEMANTIC_WINNER_ONLY'
    report['simulation_ready'] = False  # Official settlement/quotes/fees not integrated.
    completed = now if fixed_time else time.time()
    with store.db:
        store.db.execute('INSERT INTO collector_status VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',
                         (completed, json.dumps(report, allow_nan=False)))
    return report


def validate(path, now=None):
    import sqlite3
    now = time.time() if now is None else now
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True) as db:
        record = db.execute('SELECT observed_at,payload FROM collector_status WHERE singleton=1').fetchone()
        if not record:
            raise ValueError('No collection pass recorded')
        report = json.loads(record[1])
        report['status_age_seconds'] = now-record[0]
        report['status_fresh'] = 0 <= report['status_age_seconds'] <= 180
        report['collection_ready'] = (report['collection_ready'] and report['status_fresh']
                                      and set(report['streams']) == {a+'_'+d for a,d in STREAMS}
                                      and all(epoch(s['window_end']) > now for s in report['streams'].values()))
        report['verified_outcomes'] = sum(json.loads(r[0]).get('settlement_status') == 'VERIFIED' for r in db.execute("SELECT payload FROM records WHERE kind='market'"))
        report['recording_ready'] = (report.get('recording_ready',False) and report['status_fresh']
            and set(report['streams']) == {a+'_'+d for a,d in STREAMS}
            and all(epoch(s['window_end'])>now for s in report['streams'].values()))
        report['cloud_synchronized'] = (report.get('cloud_storage') == 'SYNC_BATCH_OK' and not report.get('cloud_sync',{}).get('more_possible',True))
        report['raw_quote_snapshots'] = db.execute('SELECT count(*) FROM raw_quotes').fetchone()[0]
        report['total_prediction_snapshots'] = db.execute('SELECT count(*) FROM research_snapshots').fetchone()[0]
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--record-available',action='store_true',help='Record all ten verified market subscriptions while reporting unavailable prices/quotes; not full readiness')
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--require-cloud', action='store_true', help='Validation also fails on cloud errors, disabled sync or possible backlog')
    args = parser.parse_args()
    if args.validate:
        report = validate(args.db)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if (report['recording_ready'] if args.record_available else report['collection_ready']) and (not args.require_cloud or report['cloud_synchronized']) else 1)
    store = Store(args.db)
    try:
        while True:
            import shutil
            if shutil.disk_usage(args.db.resolve().parent).free < 100*1024**2:
                print(json.dumps({'collection_ready':False,'paused_reason':'Less than 100 MiB free disk; no new writes attempted'}),flush=True)
                if not args.loop:
                    raise SystemExit(1)
                time.sleep(60)
                continue
            report = collect(store)
            import os
            if os.environ.get('BTC_RESEARCH_SYNC_ENABLED') == '1':
                from cloud_sync import Client, sync
                try:
                    report['cloud_sync'] = sync(store, Client(os.environ.get('BTC_RESEARCH_SUPABASE_URL',''),os.environ.get('BTC_RESEARCH_SUPABASE_KEY','')))
                    report['cloud_storage'] = 'SYNC_ERRORS' if report['cloud_sync']['errors'] else 'SYNC_BATCH_OK'
                except Exception as exc:
                    report['cloud_storage'] = 'ERROR_' + type(exc).__name__
            report['quote_capture_ready'] = all(s.get('quote_status') == 'RAW_BBO_SAVED_SIDE_MAPPING_PENDING' for s in report['streams'].values())
            with store.db:
                store.db.execute('UPDATE collector_status SET payload=? WHERE singleton=1', (json.dumps(report,allow_nan=False),))
            print(json.dumps(report), flush=True)
            if not args.loop:
                raise SystemExit(0 if (report['recording_ready'] if args.record_available else report['collection_ready']) else 1)
            time.sleep(60)
    finally:
        store.db.close()


if __name__ == '__main__':
    main()
