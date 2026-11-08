"""Persistent model-confidence trailing exits; depth-limited, delayed paper sells."""
from dataclasses import asdict
from decimal import Decimal,ROUND_DOWN
import json
from trading_bot.core import amount,time_of
from trading_bot.execution_model import OrderPlan,simulate,QUADRATIC_TAKER_RULE
from trading_bot.provider import FEE_BASIS


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS probability_trails (
      wallet TEXT,entry_key TEXT,peak TEXT,current TEXT,signal_at REAL,triggered_at REAL,
      PRIMARY KEY(wallet,entry_key));
      CREATE TABLE IF NOT EXISTS exit_orders (
      order_id TEXT PRIMARY KEY,wallet TEXT,entry_key TEXT,state TEXT,payload TEXT,result TEXT);''')


def update_trail(engine,wallet,key,p,data,now):
    from trading_bot.observed_paper import SETTINGS
    candidates=[s for s in data.get('predictions',[]) if s.get('market_slug')==p['market_slug'] and s.get('model_version')==p['model_version']]
    if not candidates: return
    signal=max(candidates,key=lambda s:s['recorded_at']);stamp=time_of(signal['recorded_at'])
    if not p['window_start']<=stamp<=now or not 0<=now-stamp<=90: return
    if signal.get('source_timestamp'):
        source=time_of(signal['source_timestamp'])
        if not p['window_start']<=source<=stamp or not 0<=now-source<=120: return
    up=amount(signal['predicted_up_probability'])
    if not 0<=up<=1: return
    probability=up if p['side']=='UP' else 1-up
    row=engine.db.execute('SELECT peak,current,signal_at,triggered_at FROM probability_trails WHERE wallet=? AND entry_key=?',(wallet,key)).fetchone()
    if row and stamp<=row[2]: return
    if not row:
        entry=engine.db.execute('SELECT payload FROM orders WHERE wallet=? AND market_slug=?',(wallet,key)).fetchone()
        entry=json.loads(entry[0]) if entry else {}
        original=entry.get('signal',{}).get('predicted_up_probability')
        original=amount(original) if original is not None else up
        peak=original if p['side']=='UP' else 1-original
        trigger=None
    else: peak=amount(row[0]);trigger=row[3]
    peak=max(peak,probability)
    if trigger is None and peak-probability>=Decimal(SETTINGS['trailing_probability_drop']): trigger=now
    with engine.db:
        engine.db.execute('''INSERT INTO probability_trails VALUES(?,?,?,?,?,?) ON CONFLICT(wallet,entry_key)
          DO UPDATE SET peak=excluded.peak,current=excluded.current,signal_at=excluded.signal_at,triggered_at=excluded.triggered_at''',
          (wallet,key,str(peak),str(probability),stamp,trigger))


def sell_book(book):
    return dict(book,intent='ORDER_INTENT_SELL_LONG' if book['side']=='UP' else 'ORDER_INTENT_SELL_SHORT',bids=book['liquidation_bids'])


def finish(engine,oid,wallet,key,encoded,books,now):
    plan=OrderPlan(**json.loads(encoded)['plan'])
    if now<plan.eligible_at:
        row=engine.db.execute('SELECT payload FROM positions WHERE wallet=? AND market_slug=?',(wallet,key)).fetchone()
        if row and json.loads(row[0])['state']=='PAPER_OPEN': return
    snapshot=sell_book(books[plan.side]) if plan.side in books else {}
    result=simulate(plan,snapshot,now)
    with engine.db:
        engine.db.execute('BEGIN IMMEDIATE')
        row=engine.db.execute('SELECT payload FROM positions WHERE wallet=? AND market_slug=?',(wallet,key)).fetchone()
        p=json.loads(row[0]) if row else None
        if not p or p['state']!='PAPER_OPEN':
            result.update(state='CANCELLED',filled_quantity='0',fees='0',gross_cost='0',total_cost='0',gross_proceeds='0',net_proceeds='0',fills=[],reason='POSITION_ALREADY_CLOSED')
        updated=engine.db.execute("UPDATE exit_orders SET state=?,result=? WHERE order_id=? AND state='PROPOSED'",(result['state'],json.dumps(result),oid)).rowcount
        if not updated: return
        if p and p['state']=='PAPER_OPEN' and amount(result['filled_quantity'])>0:
            if amount(result['filled_quantity'])!=amount(p['quantity']): raise ValueError('FULL_EXIT_REQUIRED')
            proceeds=amount(result['net_proceeds'])
            if proceeds<0: raise ValueError('NEGATIVE_SELL_PROCEEDS')
            trail=engine.db.execute('SELECT peak,current,triggered_at FROM probability_trails WHERE wallet=? AND entry_key=?',(wallet,key)).fetchone()
            p.update(state='PAPER_CLOSED',close_reason='MODEL_PROBABILITY_TRAILING_EXIT',closed_at=now,payout=str(proceeds),
                pnl=str(proceeds-amount(p['cost'])),exit_fees=result['fees'],exit_price=str(amount(result['gross_proceeds'])/amount(p['quantity'])),
                exit_order_id=oid,exit_fills=result['fills'],exit_policy='FOK_OBSERVED_BID_TRAILING_PROBABILITY_V1',
                signal_peak=trail[0] if trail else None,signal_at_exit=trail[1] if trail else None)
            cash=amount(engine.db.execute('SELECT cash FROM wallets WHERE name=?',(wallet,)).fetchone()[0])
            engine.db.execute('UPDATE wallets SET cash=? WHERE name=?',(str(cash+proceeds),wallet))
            engine.db.execute('UPDATE positions SET payload=? WHERE wallet=? AND market_slug=?',(json.dumps(p),wallet,key))
    engine.event(wallet,plan.market_slug,'EXIT_'+result.get('reason','UNKNOWN'),now)


def manage(engine,data,get,now,fresh,clock):
    markets={m['market_slug']:m for m in data.get('markets',[])}
    pending=engine.db.execute("SELECT order_id,wallet,entry_key,payload FROM exit_orders WHERE state='PROPOSED'").fetchall()
    for oid,wallet,key,encoded in pending:
        plan=OrderPlan(**json.loads(encoded)['plan'])
        row=engine.db.execute('SELECT payload FROM positions WHERE wallet=? AND market_slug=?',(wallet,key)).fetchone()
        opened=row and json.loads(row[0])['state']=='PAPER_OPEN'
        if now<plan.eligible_at and opened: continue
        try:
            books=get(markets[plan.market_slug],plan.eligible_at) if opened and fresh and now<plan.expires_at else {}
            finish(engine,oid,wallet,key,encoded,books,clock())
        except Exception as error:
            engine.event(wallet,plan.market_slug,'EXIT_'+(str(error) if isinstance(error,ValueError) else type(error).__name__),now)
            if now>=plan.expires_at: finish(engine,oid,wallet,key,encoded,{},now)
    if not fresh: return
    opened=[(wallet,key,json.loads(encoded)) for wallet,key,encoded in engine.db.execute('SELECT wallet,market_slug,payload FROM positions') if json.loads(encoded)['state']=='PAPER_OPEN']
    for wallet,key,p in opened: update_trail(engine,wallet,key,p,data,now)
    budget=dict(engine.db.execute('SELECT key,value FROM meta'))
    opened.sort(key=lambda row:budget.get('exit_quote:'+row[0]+':'+row[1],0))
    for wallet,key,p in opened:
        trail=engine.db.execute('SELECT peak,current,signal_at,triggered_at FROM probability_trails WHERE wallet=? AND entry_key=?',(wallet,key)).fetchone()
        if not trail or trail[3] is None: continue
        if engine.db.execute("SELECT 1 FROM exit_orders WHERE wallet=? AND entry_key=? AND state='PROPOSED'",(wallet,key)).fetchone(): continue
        if p['window_end']-now<4: continue
        try:
            m=markets[p['market_slug']];books=get(m);book=books[p['side']];bids=book.get('liquidation_bids',[])
            if not bids: raise ValueError('NO_EXIT_BIDS')
            created=clock();metadata=data.get('execution_evidence',{}).get('metadata',{}).get(m['market_slug'],{})
            tick=amount(metadata['orderPriceMinTickSize'])
            limit=max(tick,((amount(bids[0]['price'])-tick)/tick).to_integral_value(rounding=ROUND_DOWN)*tick)
            plan=OrderPlan(m['market_slug'],p['contract_slug'],p['model_version'],p['asset'],p['duration_seconds'],p['side'],
                'ORDER_INTENT_SELL_LONG' if p['side']=='UP' else 'ORDER_INTENT_SELL_SHORT',p['quantity'],str(limit),str(tick),'1',
                created,min(trail[2],created),created+2,min(created+15,p['window_end']-1),p['window_end'],
                'TIME_IN_FORCE_FILL_OR_KILL',book['mapping_evidence'],QUADRATIC_TAKER_RULE,'.06',FEE_BASIS)
            plan.validate()
            with engine.db:
                engine.db.execute('INSERT INTO exit_orders VALUES(?,?,?,?,?,NULL)',(plan.order_id,wallet,key,'PROPOSED',json.dumps(dict(plan=asdict(plan)))))
                engine.db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('exit_quote:'+wallet+':'+key,created))
            engine.event(wallet,m['market_slug'],'PROPOSED_PROBABILITY_TRAILING_EXIT',created)
        except Exception as error:
            engine.event(wallet,p['market_slug'],'EXIT_'+(str(error) if isinstance(error,ValueError) else type(error).__name__),now)


def annotate(db,reports):
    for wallet,report in reports.items():
        report['open_exit_triggers']=db.execute("SELECT count(*) FROM probability_trails t JOIN positions p ON p.wallet=t.wallet AND p.market_slug=t.entry_key WHERE t.wallet=? AND t.triggered_at IS NOT NULL AND json_extract(p.payload,'$.state')='PAPER_OPEN'",(wallet,)).fetchone()[0]
        report['exit_order_states']=dict(db.execute('SELECT state,count(*) FROM exit_orders WHERE wallet=? GROUP BY state',(wallet,)))
        report['probability_trails']=[dict(entry_key=key,peak=peak,current=current,signal_at=stamp,triggered_at=trigger)
            for key,peak,current,stamp,trigger in db.execute('SELECT entry_key,peak,current,signal_at,triggered_at FROM probability_trails WHERE wallet=? ORDER BY signal_at DESC LIMIT 10',(wallet,))]
