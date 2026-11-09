"""Polymarket current-mark band entries, fresh local lean alignment, fixed exits."""
from decimal import Decimal
import json
from trading_bot.core import amount,time_of
from trading_bot.observed_paper import SETTINGS as TRAILING_SETTINGS

BAND_SETTINGS=dict(TRAILING_SETTINGS,version='OBSERVED_PAPER_V7_FIVE_POINT_30S_45_UP',entry_strategy='MARKET_BAND',
    opening_wait_seconds=90,close_cutoff_15m=180,close_cutoff_5m=120,market_band_min='.54',market_band_max='.64',market_max_spread='.02',
    market_stop_drop='.05',market_take_profit='.75',market_profit_arm='.70',market_profit_trail='.01',market_stop_hold_seconds=30,max_entries_per_stream=5,minimum_edge_required=False)
for _obsolete in ('entry_seconds_remaining','late_entry_seconds','reversal_confidence','reversal_minimum_edge','trailing_probability_drop','minimum_edge'):
    BAND_SETTINGS.pop(_obsolete,None)


V6_BAND_SETTINGS=dict(BAND_SETTINGS,version='OBSERVED_PAPER_V6_STOP_TIMER_PROFIT_TRAIL',market_stop_drop='.03',market_stop_hold_seconds=15)
OLD_BAND_SETTINGS=dict(V6_BAND_SETTINGS,version='OBSERVED_PAPER_V5_MARKET_BAND',market_stop_drop='.02',market_take_profit='.71')
for _new in ('market_profit_arm','market_profit_trail','market_stop_hold_seconds'):
    OLD_BAND_SETTINGS.pop(_new,None)


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS current_market_lean (market_slug TEXT PRIMARY KEY,payload TEXT);
      CREATE TABLE IF NOT EXISTS market_exit_state (wallet TEXT,entry_key TEXT,payload TEXT,PRIMARY KEY(wallet,entry_key));
      CREATE TABLE IF NOT EXISTS market_entry_marks (market_slug TEXT PRIMARY KEY, observed_at REAL, up_probability TEXT);''')


def observe_lean(db,m,data,now):
    from trading_bot.dual_sandbox import RESEARCH_MODEL
    context=dict(status='NO_FRESH_LEAN',available_at=data.get('exported_at',0))
    rows=[p for p in data.get('predictions',[]) if p.get('market_slug')==m['market_slug'] and p.get('model_version')==RESEARCH_MODEL]
    if rows:
        p=max(rows,key=lambda p:p['recorded_at'])
        try:
            stamp=time_of(p['recorded_at']);source=time_of(p['source_timestamp']);features=p['feature_snapshot']
            if (features['asset']==m['asset'] and features['duration_seconds']==m['duration_seconds']
                    and amount(features['target'])==amount(m['official_price_to_beat']) and
                    time_of(m['window_start'])<=source<=stamp<=context['available_at']<=now and
                    0<=now-context['available_at']<=45 and 0<=now-stamp<=90 and 0<=now-source<=120):
                context.update(status='OK',source_model=RESEARCH_MODEL,direction=p['lean_direction'],recorded_at=stamp,source_at=source,asset=m['asset'],
                               duration_seconds=m['duration_seconds'],target=str(features['target']))
        except (KeyError,TypeError,ValueError,ArithmeticError): pass
    with db:
        db.execute('INSERT INTO current_market_lean VALUES(?,?) ON CONFLICT(market_slug) DO UPDATE SET payload=excluded.payload WHERE current_market_lean.payload!=excluded.payload',
                   (m['market_slug'],json.dumps(context)))


def mark(books,side,now):
    quote=books.get(side,{})
    if quote.get('approved') is not True or quote.get('side')!=side: raise ValueError('UNVERIFIED_MARKET_PERCENTAGE')
    stamp=quote.get('percentage_received_at')
    if stamp is None or not 0<=now-stamp<=5: raise ValueError('STALE_MARKET_PERCENTAGE')
    value=quote.get('market_up_probability')
    if value is None: raise ValueError('NO_CURRENT_MARKET_PERCENTAGE')
    up=amount(value)
    if not 0<=up<=1: raise ValueError('INVALID_MARKET_PERCENTAGE')
    return up if side=='UP' else 1-up


def entry_check(db,m,books,now,settings):
    up=mark(books,'UP',now)
    stamp=books['UP']['percentage_received_at']
    previous=db.execute('SELECT observed_at,up_probability FROM market_entry_marks WHERE market_slug=?',(m['market_slug'],)).fetchone()
    # Persist observed marks even if an entry is rejected, so crossing 45% can
    # be proven from actual fresh sequential marks rather than a model guess.
    if previous is None or stamp>previous[0]:
        with db:
            db.execute('INSERT INTO market_entry_marks VALUES(?,?,?) ON CONFLICT(market_slug) DO UPDATE SET observed_at=excluded.observed_at,up_probability=excluded.up_probability',
                       (m['market_slug'],stamp,str(up)))
    rising_45=(previous is not None and 0<stamp-previous[0]<=5
               and amount(previous[1])<Decimal('.45')<=up and up<=amount(settings['market_band_max']))
    if rising_45:
        with db: db.execute('INSERT INTO market_up_crossings VALUES(?,?) ON CONFLICT(market_slug) DO UPDATE SET crossed_at=excluded.crossed_at',(m['market_slug'],stamp))
    crossing=db.execute('SELECT crossed_at FROM market_up_crossings WHERE market_slug=?',(m['market_slug'],)).fetchone()
    rising_45=(rising_45 or (crossing is not None and 0<=stamp-crossing[0]<=15 and Decimal('.45')<=up<=Decimal('.50')))
    side='UP' if rising_45 or up>Decimal('.5') else 'DOWN'
    probability=up if side=='UP' else 1-up
    ordinary=amount(settings['market_band_min'])<=probability<=amount(settings['market_band_max'])
    if not ordinary and not rising_45:
        raise ValueError('MARKET_PERCENTAGE_OUTSIDE_ENTRY_BAND')
    selected=books[side]
    if amount(selected['offers'][0]['price'])-amount(selected['liquidation_bids'][0]['price'])>amount(settings['market_max_spread']): raise ValueError('MARKET_SPREAD_TOO_WIDE')
    row=db.execute('SELECT payload FROM current_market_lean WHERE market_slug=?',(m['market_slug'],)).fetchone()
    lean=json.loads(row[0]) if row else {}
    if (lean.get('status')!='OK' or not 0<=now-lean.get('available_at',0)<=45
            or not 0<=now-lean.get('recorded_at',0)<=90 or not 0<=now-lean.get('source_at',0)<=120):
        raise ValueError('NO_FRESH_MARKET_LEAN')
    if lean.get('direction')!=side: raise ValueError('LEAN_NOT_ALIGNED_WITH_MARKET_FAVORITE')
    return dict(side=side,market_probability=str(probability),market_source=books[side]['market_percentage_source'],lean=lean,
                rising_45_entry=rising_45)


def update_exit(engine,wallet,key,p,books,now):
    """Fixed-entry stop with continuous hold; armed peak-based profitable exit."""
    from trading_bot.execution_model import taker_fee
    entry=amount(p['entry_market_probability'])
    row=engine.db.execute('SELECT payload FROM market_exit_state WHERE wallet=? AND entry_key=?',(wallet,key)).fetchone()
    state=json.loads(row[0]) if row else dict(
        entry_probability=str(entry),
        stop_probability=str(entry-amount(p.get('exit_stop_drop','.05'))),
        take_probability=p.get('exit_target','.75'),
        profit_arm=p.get('exit_profit_arm','.70'),
        profit_trail=p.get('exit_profit_trail','.01'),
        stop_hold_seconds=p.get('exit_stop_hold_seconds',30),
        stop_since=None,profit_peak=None,triggered_at=None,reason=None)
    try:
        current=mark(books,p['side'],now)
    except ValueError:
        if state['triggered_at'] is not None: return state
        raise
    stamp=books[p['side']]['percentage_received_at']
    if stamp<state.get('observed_at',0): raise ValueError('MARKET_PERCENTAGE_CLOCK_ROLLBACK')
    legacy=p.get('exit_rule')=='MARKET_FIXED_2PT_71'
    # Never allow an old snapshot to advance the stop timer.
    if stamp==state.get('observed_at'): return state
    if state.get('stop_since') is not None and stamp-state.get('observed_at',stamp)>5:
        state['stop_since']=None
    state.update(current_probability=str(current),observed_at=stamp,source=books[p['side']]['market_percentage_source'])
    if state['triggered_at'] is None and legacy:
        if current<=amount(state['stop_probability']): state.update(triggered_at=now,reason='MARKET_ENTRY_MINUS_2_POINTS')
        elif current>=amount(state['take_probability']): state.update(triggered_at=now,reason='MARKET_71_PERCENT_TARGET')
    elif state['triggered_at'] is None:
        if current<=amount(state['stop_probability']):
            if state.get('stop_since') is None: state['stop_since']=stamp
            if stamp-state['stop_since']>=float(state['stop_hold_seconds']):
                state.update(triggered_at=now,reason=('MARKET_ENTRY_MINUS_5_POINTS_30_SECONDS' if p.get('exit_rule')=='MARKET_FIXED_5PT_30S_TRAIL_70_75' else 'MARKET_ENTRY_MINUS_3_POINTS_15_SECONDS'))
        else:
            state['stop_since']=None

        peak=amount(state['profit_peak']) if state.get('profit_peak') is not None else None
        if current>=amount(state['profit_arm']):
            peak=max(peak,current) if peak is not None else current
            state['profit_peak']=str(peak)
        if state['triggered_at'] is None and peak is not None:
            # Profitability is based on executable bid proceeds after estimated fees,
            # not on the displayed market percentage alone.
            bids=books[p['side']].get('liquidation_bids',[])
            quantity=amount(p['quantity'])
            remaining=quantity;gross=Decimal(0);fees=Decimal(0)
            for level in bids:
                take=min(remaining,amount(level['quantity']))
                if take<=0: continue
                price=amount(level['price'])
                gross+=take*price
                fees+=taker_fee('.06',take,price)
                remaining-=take
                if remaining<=0: break
            profitable=remaining==0 and gross-fees>amount(p['cost'])
            if profitable and current>=amount(state['take_probability']):
                state.update(triggered_at=now,reason='MARKET_75_PERCENT_TARGET')
            elif profitable and current>=amount(state['profit_arm']) and current<=peak-amount(state['profit_trail']):
                state.update(triggered_at=now,reason='MARKET_PROFIT_TRAIL_1_POINT')
    with engine.db:
        engine.db.execute('INSERT INTO market_exit_state VALUES(?,?,?) ON CONFLICT(wallet,entry_key) DO UPDATE SET payload=excluded.payload',
                          (wallet,key,json.dumps(state)))
    return state
