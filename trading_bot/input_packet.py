"""Bounded execution packets; collector/ledger history remains authoritative."""
import hashlib
import json
from pathlib import Path
import sqlite3
from trading_bot.core import time_of

MAX_BYTES=8_000_000
MARKET_FIELDS=('market_slug','contract_slug','asset','duration_seconds','window_start','window_end',
               'official_price_to_beat','market_type','reference_source','settlement_status',
               'official_winner','settled_at','updated_at')


def read_packet(path):
    # Read through one descriptor so an atomic exporter replacement cannot race
    # a separate stat/read and bypass the byte limit.
    with Path(path).open('rb') as stream: raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise ValueError('INPUT_TOO_LARGE')
    data=json.loads(raw)
    if not isinstance(data,dict): raise ValueError('INPUT_NOT_AN_OBJECT')
    return data


def required_markets(ledger):
    ledger=Path(ledger)
    if not ledger.exists(): return set()  # First export before engine creation.
    result=set()
    # On read failure propagate; never silently lose an outstanding settlement.
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        for slug,payload in db.execute('SELECT market_slug,payload FROM positions'):
            if json.loads(payload).get('state')=='PAPER_OPEN': result.add(json.loads(payload).get('market_slug',slug))
        result.update(json.loads(r[0])['plan']['market_slug'] for r in db.execute("SELECT payload FROM orders WHERE state='PROPOSED'"))
    return result


def compact_markets(rows,now,required=()):
    result=[];seen=set()
    for m in rows:
        slug=m['market_slug']
        if slug not in required and time_of(m['window_end'])<now-86400: continue
        item={k:m[k] for k in MARKET_FIELDS if k in m}
        evidence=m.get('settlement_evidence')
        if evidence:
            raw=evidence if isinstance(evidence,str) else json.dumps(evidence,sort_keys=True,allow_nan=False)
            item['settlement_evidence']=dict(sha256=hashlib.sha256(raw.encode()).hexdigest(),
                archive='research.sqlite records.market settlement_evidence',market_slug=slug)
        result.append(item);seen.add(slug)
    missing=set(required)-seen
    if missing: raise ValueError('OPEN_MARKET_MISSING_FROM_COLLECTOR:'+str(len(missing)))
    return result


def encode_packet(data):
    raw=json.dumps(data,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>MAX_BYTES: raise ValueError('EXPORT_EXCEEDS_ENGINE_INPUT_LIMIT')
    return raw
