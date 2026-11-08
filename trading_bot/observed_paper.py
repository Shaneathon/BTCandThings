"""Forward observed-book paper engine. Public GETs only; persistent order journal."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
from decimal import Decimal,ROUND_DOWN
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote
from urllib.request import Request,urlopen
from email.utils import parsedate_to_datetime
from trading_bot.core import amount,time_of,verified
from trading_bot.dual_sandbox import MODELS,MARKET_STREAMS,RESEARCH_MODEL
from trading_bot.execution_model import OrderPlan,QUADRATIC_TAKER_RULE,simulate,taker_fee
from trading_bot.provider import directional_book,mapping,FEE_BASIS
from trading_bot.market_pnl import summarize

LEGACY_SETTINGS=dict(version='OBSERVED_PAPER_V1',initial_cash='1000',max_trade_cost='10',max_open=1,
              max_daily_loss='100',max_drawdown='.10',minimum_edge='.03',latency_seconds=2,
              max_signal_age=90,quote_limit_allowance='.01',participation='.25',fee='.06',
              fee_basis=FEE_BASIS,entry_seconds_remaining=[30,90],order_ttl_seconds=15)
PREVIOUS_SETTINGS=dict(LEGACY_SETTINGS,version='OBSERVED_PAPER_V2_050_5',min_trade_cost='0.50',max_trade_cost='5')
SETTINGS=dict(PREVIOUS_SETTINGS,version='OBSERVED_PAPER_V3_FIXED_150',target_trade_cost='1.50',max_trade_cost='1.50')


def slots():
    return {**{name:('BTC',900,model) for name,model in MODELS.items()},
            **{asset+'_'+str(duration//60)+'m':(asset,duration,RESEARCH_MODEL) for asset,duration in MARKET_STREAMS}}


class Engine:
    def __init__(self,path):
        expected=json.dumps(SETTINGS,sort_keys=True)
        from trading_bot.ledger_guard import check_existing
        check_existing(path,expected)
        self.db=sqlite3.connect(path,timeout=15)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,payload TEXT);
          CREATE TABLE IF NOT EXISTS configuration_history(id INTEGER PRIMARY KEY,changed_at REAL,previous TEXT,current TEXT,reason TEXT);
          CREATE TABLE IF NOT EXISTS wallets(name TEXT PRIMARY KEY,cash TEXT,high TEXT,halted TEXT);
          CREATE TABLE IF NOT EXISTS orders(wallet TEXT,market_slug TEXT,state TEXT,payload TEXT,result TEXT,PRIMARY KEY(wallet,market_slug));
          CREATE TABLE IF NOT EXISTS positions(wallet TEXT,market_slug TEXT,payload TEXT,PRIMARY KEY(wallet,market_slug));
          CREATE TABLE IF NOT EXISTS events(wallet TEXT,market_slug TEXT,reason TEXT,observed_at REAL,PRIMARY KEY(wallet,market_slug,reason));
          CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY,observed_at REAL,payload TEXT);
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value REAL);
          CREATE TABLE IF NOT EXISTS bot_snapshot(id INTEGER PRIMARY KEY,observed_at REAL,payload TEXT);
        ''')
        from trading_bot.automatic_review import initialize
        initialize(self.db)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO settings VALUES(1,?)',(expected,))
            for name in slots(): self.db.execute('INSERT OR IGNORE INTO wallets VALUES(?,?,?,NULL)',(name,'1000','1000'))

    def close(self): self.db.close()

    def event(self,wallet,slug,reason,now):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?)',(wallet,slug,str(reason),now))

    def settle(self,markets,now):
        lookup={m['market_slug']:m for m in markets}
        with self.db:
            for wallet,slug,payload in self.db.execute('SELECT wallet,market_slug,payload FROM positions').fetchall():
                p=json.loads(payload);m=lookup.get(slug)
                if p['state']!='PAPER_OPEN' or not m: continue
                try:
                    if (not verified(m,now) or m['contract_slug']!=p['contract_slug'] or m['asset']!=p['asset']
                            or m['duration_seconds']!=p['duration_seconds'] or time_of(m['window_start'])!=p['window_start']
                            or time_of(m['window_end'])!=p['window_end']
                            or amount(m['official_price_to_beat'])!=amount(p['price_to_beat'])): continue
                except (KeyError,ValueError,TypeError,ArithmeticError): continue
                payout=amount(p['quantity']) if m['official_winner']==p['side'] else Decimal(0)
                p.update(state='PAPER_CLOSED',payout=str(payout),pnl=str(payout-amount(p['cost'])),closed_at=now)
                cash=amount(self.db.execute('SELECT cash FROM wallets WHERE name=?',(wallet,)).fetchone()[0])
                self.db.execute('UPDATE wallets SET cash=? WHERE name=?',(str(cash+payout),wallet))
                self.db.execute('UPDATE positions SET payload=? WHERE wallet=? AND market_slug=?',(json.dumps(p),wallet,slug))

    def risk(self,wallet,now):
        cash,high,halted=self.db.execute('SELECT cash,high,halted FROM wallets WHERE name=?',(wallet,)).fetchone()
        cash,high=amount(cash),amount(high)
        positions=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM positions WHERE wallet=?',(wallet,))]
        exposure=sum((amount(p['cost']) for p in positions if p['state']=='PAPER_OPEN'),Decimal(0))
        high=max(high,cash+exposure)
        daily=sum((Decimal(p['pnl']) for p in positions if p['state']=='PAPER_CLOSED'
                   and datetime.fromtimestamp(p['closed_at'],timezone.utc).date()==datetime.fromtimestamp(now,timezone.utc).date()),Decimal(0))
        if (high-cash-exposure)/high>=Decimal('.10'): halted='MAX_REALIZED_DRAWDOWN'
        with self.db: self.db.execute('UPDATE wallets SET high=?,halted=? WHERE name=?',(str(high),halted,wallet))
        pending=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM orders WHERE wallet=? AND state='PROPOSED'",(wallet,))]
        reserve=sum((amount(p['reserve']) for p in pending),Decimal(0))
        capacity=min(Decimal(SETTINGS['max_trade_cost']),cash-reserve,Decimal(10)-exposure-reserve,
                     Decimal(100)+daily-exposure-reserve,high*Decimal('.10')-(high-cash-exposure)-exposure-reserve)
        from trading_bot.automatic_review import pause
        if pause(self.db,wallet,now): capacity=Decimal(0)
        if halted or any(p['state']=='PAPER_OPEN' for p in positions) or pending: capacity=Decimal(0)
        return max(Decimal(0),capacity)

    def propose(self,wallet,m,p,details,books,now,available_at):
        if self.db.execute('SELECT 1 FROM orders WHERE wallet=? AND market_slug=?',(wallet,m['market_slug'])).fetchone(): return
        when=time_of(p['recorded_at']);end=time_of(m['window_end']);start=time_of(m['window_start'])
        if not 0<=now-available_at<=45 or not start<=when<=available_at<=now or not 0<=now-when<=90:
            raise ValueError('STALE_OR_FUTURE_SIGNAL')
        if not 30<=end-now<=90 or m.get('settlement_status')!='PENDING': raise ValueError('ENTRY_WINDOW')
        if p.get('source_timestamp') and not start<=time_of(p['source_timestamp'])<=when: raise ValueError('INVALID_SOURCE_TIME')
        if p.get('source_timestamp') and now-time_of(p['source_timestamp'])>120: raise ValueError('STALE_FEATURES')
        up=amount(p['predicted_up_probability'])
        if not 0<=up<=1 or up==Decimal('.5'): raise ValueError('NO_DIRECTION')
        side='UP' if up>Decimal('.5') else 'DOWN';probability=up if side=='UP' else 1-up
        book=books[side];best=amount(book['offers'][0]['price'])
        tick=amount(details['orderPriceMinTickSize']);provider_min=amount(details['minimumTradeQty'])
        if tick<=0 or provider_min<=0: raise ValueError('INVALID_TRADING_MINIMUMS')
        limit=(min(Decimal('.99'),best+Decimal('.01'))/tick).to_integral_value(rounding=ROUND_DOWN)*tick
        if limit<best: raise ValueError('UNREACHABLE_LIMIT')
        # Reserve worst fee plus cent-rounding allowance for each visible level.
        capacity=self.risk(wallet,now)
        # Whole-contract fills: reserve up to 1.5c fee plus 0.5c rounding
        # allowance per contract, even if future depth splits into more levels.
        quantity=(capacity/(limit+Decimal('.020'))).to_integral_value(rounding=ROUND_DOWN)
        if quantity<max(Decimal(1),provider_min): raise ValueError('RISK_OR_MINIMUM_SIZE')
        proposed_cost=quantity*best+taker_fee('.06',quantity,best)
        if proposed_cost<Decimal(SETTINGS['min_trade_cost']): raise ValueError('BELOW_MINIMUM_PROPOSED_TRADE_COST')
        estimated=taker_fee('.06',quantity,limit)
        if probability-limit-estimated/quantity<Decimal('.03'): raise ValueError('NO_NET_EDGE')
        plan=OrderPlan(m['market_slug'],m['contract_slug'],p['model_version'],m['asset'],m['duration_seconds'],side,
              book['intent'],str(quantity),str(limit),str(tick),'1',now,when,now+2,min(now+15,end-1),end,
              'TIME_IN_FORCE_IMMEDIATE_OR_CANCEL',book['mapping_evidence'],QUADRATIC_TAKER_RULE,'.06',FEE_BASIS)
        plan.validate()
        reserve=quantity*(limit+Decimal('.020'))
        payload=dict(plan=asdict(plan),market=m,reserve=str(reserve),signal=p,available_at=available_at,initial_book=book,
                     entry_limits=dict(version=SETTINGS['version'],minimum_proposed_cost=SETTINGS['min_trade_cost'],maximum_total_cost=SETTINGS['max_trade_cost'],target_cost=SETTINGS.get('target_trade_cost'),estimated_proposed_cost=str(proposed_cost)),
                     api_fee_coefficient=details.get('feeCoefficient'),provider_minimum_quantity=str(provider_min),
                     legacy_feature_time_unknown=not bool(p.get('source_timestamp')))
        with self.db:
            self.db.execute('INSERT INTO orders VALUES(?,?,?,?,NULL)',(wallet,m['market_slug'],'PROPOSED',json.dumps(payload)))
        self.event(wallet,m['market_slug'],'PROPOSED_OBSERVED_LIMIT',now)

    def complete(self,wallet,slug,payload,books,now,blocked=False):
        record=json.loads(payload);plan=OrderPlan(**record['plan'])
        if not blocked and now<plan.eligible_at: return
        snapshot=books.get(plan.side,{}) if not blocked else {}
        result=simulate(plan,snapshot,now)
        result['book_received_at']=snapshot.get('received_at')
        result['book_requested_at']=snapshot.get('request_started_at')
        if blocked: result.update(state='REJECTED',reason='PAUSED_OR_STALE_INPUT')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            from trading_bot.automatic_review import pause
            if pause(self.db,wallet,now):
                result=simulate(plan,{},now)
                result.update(state='REJECTED',reason='AUTOMATIC_ENTRY_PAUSE')
            # Conditional transition is the exactly-once guard after restarts.
            updated=self.db.execute("UPDATE orders SET state=?,result=? WHERE wallet=? AND market_slug=? AND state='PROPOSED'",
                                    (result['state'],json.dumps(result),wallet,slug)).rowcount
            if not updated: return
            if amount(result['filled_quantity'])>0:
                cost=amount(result['total_cost']);m=record['market']
                cash=amount(self.db.execute('SELECT cash FROM wallets WHERE name=?',(wallet,)).fetchone()[0])
                if cost>amount(record['reserve']) or cost>cash or cost>Decimal(SETTINGS['max_trade_cost']): raise ValueError('FILL_EXCEEDS_RESERVED_CASH')
                qty=amount(result['filled_quantity'])
                alternate=record.get('api_fee_coefficient')
                sensitivity=None
                if alternate is not None:
                    sensitivity=str(sum((taker_fee(alternate,f['quantity'],f['price']) for f in result['fills']),Decimal(0)))
                position=dict(market_slug=slug,contract_slug=m['contract_slug'],asset=m['asset'],duration_seconds=m['duration_seconds'],
                              model_version=plan.strategy_version,entry_limits=record.get('entry_limits'),side=plan.side,state='PAPER_OPEN',quantity=str(qty),
                              entry_price=str(amount(result['gross_cost'])/qty),fees=result['fees'],cost=str(cost),opened_at=now,
                              window_start=time_of(m['window_start']),window_end=time_of(m['window_end']),
                              price_to_beat=str(m['official_price_to_beat']),order_id=plan.order_id,
                              fees_at_api_coefficient=sensitivity,api_fee_coefficient=alternate,fee_basis=FEE_BASIS,
                              simulated_only=True,price_basis='OBSERVED_POST_DELAY_BOOK',fills=result['fills'])
                self.db.execute('INSERT INTO positions VALUES(?,?,?)',(wallet,slug,json.dumps(position)))
                self.db.execute('UPDATE wallets SET cash=? WHERE name=?',(str(cash-cost),wallet))
        self.event(wallet,slug,result['reason'],now)

    def report(self,now,input_fresh):
        reports={}
        for name,(asset,duration,model) in slots().items():
            self.risk(name,now)
            cash,high,halted=self.db.execute('SELECT cash,high,halted FROM wallets WHERE name=?',(name,)).fetchone()
            positions=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM positions WHERE wallet=?',(name,))]
            opened=[p for p in positions if p['state']=='PAPER_OPEN']
            pending=[json.loads(r[0]) for r in self.db.execute("SELECT payload FROM orders WHERE wallet=? AND state='PROPOSED'",(name,))]
            states=dict(self.db.execute('SELECT state,count(*) FROM orders WHERE wallet=? GROUP BY state',(name,)))
            events=[dict(market_slug=s,reason=r,observed_at=t) for s,r,t in self.db.execute('SELECT market_slug,reason,observed_at FROM events WHERE wallet=? ORDER BY observed_at DESC LIMIT 10',(name,))]
            from trading_bot.automatic_review import pause
            reports[name]=dict(automatic_entry_pause=pause(self.db,name,now),account=dict(cash=cash,high_water=high,halted_reason=halted,
                    open_exposure=str(sum((amount(p['cost']) for p in opened),Decimal(0))),
                    reserved_cash=str(sum((amount(p['reserve']) for p in pending),Decimal(0))),
                    realized_pnl=str(sum((Decimal(p['pnl']) for p in positions if p['state']=='PAPER_CLOSED'),Decimal(0))),
                    market_pnl=summarize(positions,streams=[(asset,duration)]),positions=positions[-30:],live_orders_enabled=False),
                    model_version=model,order_states=states,decisions=events)
        report=dict(observed_at=now,operation_mode='OBSERVED_BOOK_PAPER',input_status='FRESH' if input_fresh else 'STALE',
                    account=dict(mode='PAPER',venue='Polymarket US',live_orders_enabled=False),portfolios=reports,
                    configuration=SETTINGS,fee_basis=FEE_BASIS,
                    limitations=['Observed REST books do not guarantee exchange acceptance or actual queue fills.',
                                 '25% visible-size participation, two-second minimum latency, 15-second IOC lifetime are model assumptions.',
                                 'One simulated execution per price level; real fill partition and fee rounding may differ.',
                                 '0.06 published fee basis; API coefficient retained as a separate fee sensitivity, not silently discarded.',
                                 'Separate virtual wallets, not one funded account; realized/cost-basis accounting, not live marked equity.',
                                 'Legacy Champion/B feature timestamps are unavailable; publication and first observation times are checked.',
                                 'Rule-template direction mapping requires both UP and DOWN resolved-contract corroboration.'])
        policy=self.db.execute('SELECT changed_at FROM configuration_history ORDER BY id DESC LIMIT 1').fetchone()
        report['entry_policy_changed_at']=policy[0] if policy else None
        from trading_bot.automatic_review import latest
        report['automatic_review']=latest(self.db)
        with self.db: self.db.execute('INSERT INTO bot_snapshot VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',(now,json.dumps(report)))
        return report


class BookClient:
    def __init__(self,engine): self.engine=engine;self.cache={}
    def load(self,m,details,proof,after=0):
        reviewed=mapping(m,details,proof)
        now=time.time();cached=self.cache.get(m['contract_slug'])
        if cached and cached['UP']['mapping_evidence']==reviewed and cached['UP']['request_started_at']>=after and now-cached['UP']['received_at']<=2:
            return cached
        rows=dict(self.engine.db.execute('SELECT key,value FROM meta'))
        if now<rows.get('retry_until',0): raise ValueError('RATE_LIMIT_COOLDOWN')
        if now-rows.get('last_request',0)<3: raise ValueError('REQUEST_SPACING')
        import shutil
        database_path=self.engine.db.execute('PRAGMA database_list').fetchone()[2]
        if database_path:
            path=Path(database_path)
            used=sum(p.stat().st_size for p in (path,Path(str(path)+'-wal')) if p.exists())
            if used>1024**3 or shutil.disk_usage(path.parent).free<4*1024**3: raise ValueError('QUOTE_ARCHIVE_STORAGE_BUDGET')
        requested=time.time()
        with self.engine.db: self.engine.db.execute("INSERT INTO meta VALUES('last_request',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(requested,))
        from trading_bot.book_request import request as make_book_request
        request=make_book_request(m['contract_slug'])
        try:
            with urlopen(request,timeout=5) as response:
                raw=response.read(4_000_001)
                if len(raw)>4_000_000: raise ValueError('BOOK_TOO_LARGE')
                received=time.time()
                date=response.headers.get('Date')
                if not date or not -5<=received-parsedate_to_datetime(date).timestamp()<=5: raise ValueError('STALE_HTTP_RESPONSE')
                if float(response.headers.get('Age','0'))>5: raise ValueError('CACHED_BOOK')
                data=json.loads(raw)
        except Exception as error:
            if getattr(error,'code',None)==429:
                from trading_bot.execution_audit import retry_time
                with self.engine.db: self.engine.db.execute("INSERT INTO meta VALUES('retry_until',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(retry_time(error,time.time()),))
            raise
        result=directional_book(m,details,proof,data,requested,received)
        with self.engine.db: self.engine.db.execute('INSERT INTO books(observed_at,payload) VALUES(?,?)',(received,json.dumps(dict(market=m,details=details,proof=proof,raw=data,normalized=result))))
        self.cache[m['contract_slug']]=result
        if len(self.cache)>20: self.cache={m['contract_slug']:result}
        return result


def cycle(engine,data,client,now,paused=False):
    last=engine.db.execute("SELECT value FROM meta WHERE key='last_cycle'").fetchone()
    if last and now<last[0]: raise ValueError('CLOCK_MOVED_BACKWARDS')
    with engine.db: engine.db.execute("INSERT INTO meta VALUES('last_cycle',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now,))
    fresh=0<=now-data.get('exported_at',0)<=45
    markets=data.get('markets',[]);engine.settle(markets,now)
    evidence=data.get('execution_evidence',{});metadata=evidence.get('metadata',{});proofs=evidence.get('proofs',{})
    lookup={m['market_slug']:m for m in markets}
    def get(m,after=0):
        if m['market_slug'] not in metadata: raise ValueError('MISSING_CURRENT_CONTRACT_EVIDENCE')
        return client.load(m,metadata[m['market_slug']],proofs.get(m['asset']+'_'+str(m['duration_seconds']//60)+'m',{}),after)
    for wallet,slug,payload in engine.db.execute("SELECT wallet,market_slug,payload FROM orders WHERE state='PROPOSED'").fetchall():
        plan=OrderPlan(**json.loads(payload)['plan'])
        if now<plan.eligible_at: continue
        try:
            books={} if paused or not fresh or now>=plan.expires_at else get(lookup[slug],plan.eligible_at)
            engine.complete(wallet,slug,payload,books,time.time() if client.__class__ is BookClient else now,blocked=paused or not fresh)
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) else type(error).__name__
            engine.event(wallet,slug,reason,now)
            # Spacing is scheduling, not an attempted order. Other missing-data
            # cases remain pending only until their frozen expiry, then reject.
            if now>=plan.expires_at: engine.complete(wallet,slug,payload,{},now)
    if fresh and not paused:
        candidates=[]
        for wallet,(asset,duration,model) in slots().items():
            matches=[p for p in data.get('predictions',[]) if p.get('model_version')==model and p.get('market_slug') in lookup
                     and lookup[p['market_slug']].get('asset')==asset and lookup[p['market_slug']].get('duration_seconds')==duration]
            if not matches:
                engine.event(wallet,asset+'_'+str(duration//60)+'m','NO_FRESH_PREDICTION',now)
                continue
            p=max(matches,key=lambda p:p['recorded_at']);m=lookup[p['market_slug']]
            if wallet in MODELS and not all(any(other.get('model_version')==control and other.get('market_slug')==m['market_slug']
                    and 0<=now-time_of(other['recorded_at'])<=90 for other in data.get('predictions',[])) for control in MODELS.values()):
                engine.event(wallet,m['market_slug'],'MISSING_PAIRED_CONTROL_SIGNAL',now)
                continue
            if not 30<=time_of(m['window_end'])-now<=90: continue
            if engine.db.execute('SELECT 1 FROM orders WHERE wallet=? AND market_slug=?',(wallet,m['market_slug'])).fetchone(): continue
            previous=engine.db.execute('SELECT MAX(observed_at) FROM events WHERE wallet=?',(wallet,)).fetchone()[0] or 0
            candidates.append((previous,wallet,m,p))
        for _,wallet,m,p in sorted(candidates,key=lambda c:c[0]):
            try:
                if not 0<=now-time_of(p['recorded_at'])<=90: raise ValueError('STALE_SIGNAL')
                if engine.risk(wallet,now)<=0: raise ValueError('RISK_LIMIT')
                books=get(m)
                engine.propose(wallet,m,p,metadata[m['market_slug']],books,
                               time.time() if client.__class__ is BookClient else now,data['exported_at'])
                break
            except Exception as error:
                engine.event(wallet,m['market_slug'],str(error) if isinstance(error,ValueError) else type(error).__name__,now)
    result=engine.report(time.time() if client.__class__ is BookClient else now,fresh)
    if data.get('input_error'):
        result['input_error']=data['input_error']
        with engine.db: engine.db.execute('UPDATE bot_snapshot SET payload=? WHERE id=1',(json.dumps(result),))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--kill-file',type=Path,required=True)
    args=parser.parse_args();engine=Engine(args.ledger);client=BookClient(engine)
    try:
        while True:
            from trading_bot.input_packet import read_packet
            try:
                data=read_packet(args.input)
            except (OSError,ValueError) as error:
                data=dict(input_error='INPUT_TOO_LARGE' if str(error)=='INPUT_TOO_LARGE' else 'INPUT_UNREADABLE_OR_INVALID')
            report=cycle(engine,data,client,time.time(),paused=args.kill_file.exists())
            print(json.dumps(dict(mode=report['operation_mode'],input=report['input_status'],live_orders=False)),flush=True)
            time.sleep(1)
    finally: engine.close()

if __name__=='__main__': main()
