"""Archive exact-contract BBO evidence, without assuming LONG/SHORT side mapping.

Route/response shape verified against polymarket-us 2.4.1 SDK source, not a live
response. Raw bids/asks are not automatically promoted to simulation fills.
"""
import json
import math
import time
from urllib.parse import quote
from collector import iso, epoch


def capture(store,get,market,observed=None):
    contract=market['contract_slug']
    response=get('https://gateway.polymarket.us/v1/markets/'+quote(contract,safe='')+'/bbo')
    observed=time.time() if observed is None else observed
    md=response.get('marketData') if isinstance(response,dict) else None
    if not isinstance(md,dict) or md.get('marketSlug')!=contract:
        raise ValueError('BBO contract identity unverified')
    values=[]
    for key in ('bestBid','bestAsk'):
        value=md.get(key)
        raw=value.get('value') if isinstance(value,dict) else value
        if raw is None or raw == '':
            raise ValueError('BBO '+key+' unavailable; no executable price')
        try:
            number=float(raw)
        except (TypeError,ValueError) as exc:
            raise ValueError('Invalid BBO '+key+' price') from exc
        if not math.isfinite(number) or not 0<=number<=1:
            raise ValueError('Invalid BBO price')
        values.append(number)
    if values[0]>values[1]:
        raise ValueError('Crossed BBO')
    row=dict(market_slug=market['market_slug'],contract_slug=contract,captured_at=iso(observed),
             source_name='Polymarket US',side_mapping_verified=False,raw=response)
    with store.db:
        store.db.execute('INSERT OR IGNORE INTO raw_quotes VALUES (?,?,?)',
                         (row['market_slug'],row['captured_at'],json.dumps(row,allow_nan=False)))
    return row


class QuoteCooldown(Exception):
    code=429
    def __init__(self,retry_until):
        self.retry_until=retry_until
        super().__init__('Quote requests cooling down')


def initialize_budget(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS quote_budget (id INTEGER PRIMARY KEY,last_attempt REAL,retry_until REAL)')
    store.db.execute('CREATE TABLE IF NOT EXISTS quote_checks (stream TEXT PRIMARY KEY,last_attempt REAL)')
    store.db.commit()


def last_attempt(store,market):
    stream=market['asset']+'_'+str(market['duration_seconds'])
    row=store.db.execute('SELECT last_attempt FROM quote_checks WHERE stream=?',(stream,)).fetchone()
    return row[0] if row else 0


def capture_managed(store,get,market,observed=None,minimum_interval=1.5):
    from email.utils import parsedate_to_datetime
    from datetime import timezone
    fixed=observed is not None
    now=observed if fixed else time.time()
    budget=store.db.execute('SELECT last_attempt,retry_until FROM quote_budget WHERE id=1').fetchone()
    if budget and budget[1]>now: raise QuoteCooldown(budget[1])
    if not fixed and budget:
        pause=minimum_interval-(now-budget[0])
        if pause>0: time.sleep(min(pause,minimum_interval))
        now=time.time()
    if now>=epoch(market['window_end']):
        raise ValueError('Quote market window has closed')
    stream=market['asset']+'_'+str(market['duration_seconds'])
    with store.db:
        store.db.execute('INSERT INTO quote_budget VALUES (1,?,0) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt',(now,))
        store.db.execute('INSERT INTO quote_checks VALUES (?,?) ON CONFLICT(stream) DO UPDATE SET last_attempt=excluded.last_attempt',(stream,now))
    try:
        return capture(store,get,market,now if fixed else None)
    except Exception as exc:
        if getattr(exc,'code',None)==429:
            retry=now+60
            raw=(getattr(exc,'headers',None) or {}).get('Retry-After')
            if raw:
                try: retry=now+max(0,int(raw))
                except (ValueError,TypeError):
                    try:
                        stamp=parsedate_to_datetime(raw)
                        if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
                        retry=max(now,stamp.timestamp())
                    except (ValueError,TypeError,OverflowError): pass
            with store.db:
                store.db.execute('UPDATE quote_budget SET retry_until=? WHERE id=1',(retry,))
            exc.retry_until=retry
        raise
