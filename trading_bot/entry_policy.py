"""Full-window entry checks and per-stream rolling entry budget."""
from decimal import Decimal
import json
from trading_bot.core import amount,time_of


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS signal_observations (
      wallet TEXT,market_slug TEXT,recorded_at REAL,first_seen REAL,probability TEXT,
      PRIMARY KEY(wallet,market_slug,recorded_at))''')


def observe(db,wallet,m,p,now,available):
    stamp=time_of(p['recorded_at']);up=amount(p['predicted_up_probability'])
    if not (time_of(m['window_start'])<=stamp<=available<=now and 0<=now-available<=45 and 0<=now-stamp<=90 and 0<=up<=1): return
    with db:
        db.execute('INSERT OR IGNORE INTO signal_observations VALUES(?,?,?,?,?)',(wallet,m['market_slug'],stamp,now,str(up)))


def phase(db,wallet,m,p,now,settings):
    remaining=time_of(m['window_end'])-now
    if not settings['entry_seconds_remaining'][0]<=remaining<=m['duration_seconds']:
        raise ValueError('ENTRY_WINDOW')
    if remaining>settings['late_entry_seconds']: return dict(phase='NORMAL',minimum_edge=settings['minimum_edge'])
    current=amount(p['predicted_up_probability']);stamp=time_of(p['recorded_at'])
    confidence=max(current,1-current);threshold=Decimal(settings['reversal_confidence'])
    if not 0<=now-stamp<=30 or confidence<threshold: raise ValueError('LATE_REVERSAL_REQUIRED')
    previous=db.execute('''SELECT recorded_at,probability,first_seen FROM signal_observations
      WHERE wallet=? AND market_slug=? AND recorded_at<? AND recorded_at>=? AND first_seen<=?
      ORDER BY recorded_at DESC''',(wallet,m['market_slug'],stamp,now-120,now)).fetchall()
    for when,encoded,seen in previous:
        up=amount(encoded)
        if (up<Decimal('.5'))!=(current<Decimal('.5')) and max(up,1-up)>=threshold:
            return dict(phase='LATE_MODEL_REVERSAL',minimum_edge=settings['reversal_minimum_edge'],previous_probability=str(up),
                        previous_recorded_at=when,previous_first_seen=seen,current_probability=str(current),current_recorded_at=stamp)
    raise ValueError('LATE_REVERSAL_REQUIRED')


def reserve_slot(db,wallet,m,now,settings):
    """Called under the same write lock as order insertion; pending orders reserve slots."""
    cutoff=now-settings['entry_budget_seconds']
    filled=db.execute('''SELECT count(*) FROM positions WHERE json_extract(payload,'$.asset')=?
      AND json_extract(payload,'$.duration_seconds')=? AND CAST(json_extract(payload,'$.opened_at') AS REAL)>?
      AND CAST(json_extract(payload,'$.opened_at') AS REAL)<=?''',(m['asset'],m['duration_seconds'],cutoff,now)).fetchone()[0]
    pending=db.execute('''SELECT count(*) FROM orders WHERE state='PROPOSED' AND json_extract(payload,'$.plan.asset')=?
      AND json_extract(payload,'$.plan.duration_seconds')=?''',(m['asset'],m['duration_seconds'])).fetchone()[0]
    if filled+pending>=settings['max_entries_per_stream']: raise ValueError('ROLLING_MARKET_ENTRY_LIMIT')
    rows=db.execute('''SELECT payload FROM orders WHERE wallet=? AND json_extract(payload,'$.plan.market_slug')=?''',(wallet,m['market_slug'])).fetchall()
    if any(now-json.loads(row[0])['plan']['created_at']<15 for row in rows): raise ValueError('ENTRY_RETRY_SPACING')
    index=len(rows)+1
    return m['market_slug'] if index==1 else m['market_slug']+'::entry'+str(index)
