"""Persistent, capital-constrained paper trading. No exchange or network calls."""
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

STREAMS={(a,d) for a in ('BTC','ETH','XRP','SOL') for d in (300,900)} | {('GOLD',900),('SILVER',900)}


def time_of(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timezone required')
    return t.timestamp()


def amount(value):
    if isinstance(value,bool):
        raise ValueError('Boolean amount')
    result=Decimal(str(value))
    if not result.is_finite() or result<0:
        raise ValueError('Invalid nonnegative amount')
    return result


@dataclass(frozen=True)
class Config:
    initial_cash: str = '1000'
    max_trade_cost: str = '10'
    max_exposure: str = '100'
    max_open_positions: int = 10
    max_daily_loss: str = '100'
    max_drawdown: str = '0.10'
    minimum_edge: str = '0.05'
    maximum_spread: str = '0.10'
    minimum_settled_markets: int = 30
    maximum_brier: float = .25
    max_prediction_age: int = 90
    max_quote_age: int = 15
    max_source_age: int = 120
    minimum_seconds_remaining: int = 30
    fee_per_share: str = '0.01'
    slippage_per_share: str = '0.01'
    model_version: str = 'Multi-asset spot baseline research V1'
    require_lean_alignment: bool = True

    def validate(self):
        for key in ('initial_cash','max_trade_cost','max_exposure','max_daily_loss','max_drawdown',
                    'minimum_edge','maximum_spread','fee_per_share','slippage_per_share'):
            amount(getattr(self,key))
        if not 0<amount(self.max_drawdown)<1 or not 0<amount(self.initial_cash):
            raise ValueError('Invalid bankroll or drawdown fraction')
        if not 0<amount(self.max_trade_cost)<=amount(self.max_exposure)<=amount(self.initial_cash):
            raise ValueError('Invalid exposure limits')
        for key in ('max_open_positions','minimum_settled_markets','max_prediction_age','max_quote_age','max_source_age','minimum_seconds_remaining'):
            value=getattr(self,key)
            if type(value) is not int or value<1:
                raise ValueError('Positive integer limit required')
        if type(self.require_lean_alignment) is not bool or not isinstance(self.model_version,str) or not self.model_version:
            raise ValueError('Invalid strategy selection')
        if amount(self.minimum_edge)>1 or amount(self.maximum_spread)>1:
            raise ValueError('Probability limits must be at most one')
        if not math.isfinite(self.maximum_brier) or not 0<=self.maximum_brier<=1:
            raise ValueError('Invalid Brier threshold')
        return self


def verified(market,now):
    return (market.get('settlement_status')=='VERIFIED' and market.get('official_winner') in ('UP','DOWN')
            and bool(market.get('settlement_evidence')) and market.get('settled_at')
            and time_of(market['window_end'])<=time_of(market['settled_at'])<=now)


def historical_score(markets,predictions,current,model,phase,now,max_source_age=120):
    selected={}
    for p in predictions:
        m=markets.get(p.get('market_slug'))
        if (not m or m['market_slug']==current['market_slug'] or m.get('asset')!=current['asset']
                or m.get('duration_seconds')!=current['duration_seconds'] or p.get('model_version')!=model):
            continue
        try:
            if not verified(m,now):
                continue
            when=time_of(p['recorded_at'])
            start,end=time_of(m['window_start']),time_of(m['window_end'])
            source=time_of(p['source_timestamp'])
            if not start<=when<end or not start<=source<=when or when-source>max_source_age:
                continue
            if int((when-start)/(m['duration_seconds']/5))!=phase:
                continue
            probability=amount(p['predicted_up_probability'])
            if probability>1:
                continue
            old=selected.get(m['market_slug'])
            if old is None or when<old[0]:
                selected[m['market_slug']]=(when,probability,int(m['official_winner']=='UP'))
        except (KeyError,ValueError,TypeError,ArithmeticError):
            continue
    n=len(selected)
    brier=sum((float(p)-y)**2 for _,p,y in selected.values())/n if n else None
    return {'markets':n,'brier':brier,'phase':phase}


class PaperBot:
    def __init__(self,path,config=None):
        self.config=(config or Config()).validate()
        from trading_bot.ledger_guard import check_existing
        check_existing(path,json.dumps(asdict(self.config),sort_keys=True))
        self.db=sqlite3.connect(path,timeout=15)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT);
          CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, cash TEXT, high_water TEXT, halted TEXT);
          CREATE TABLE IF NOT EXISTS positions (market_slug TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS bot_snapshot (id INTEGER PRIMARY KEY, observed_at REAL, payload TEXT);
          CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, observed_at REAL, payload TEXT);
        ''')
        configured=json.dumps(asdict(self.config),sort_keys=True)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO settings VALUES (1,?)',(configured,))
            if self.db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]!=configured:
                raise ValueError('Configuration differs from existing ledger; preserve it or use a separate ledger')
            self.db.execute('INSERT OR IGNORE INTO account VALUES (1,?,?,NULL)',(self.config.initial_cash,self.config.initial_cash))

    def close(self):
        self.db.close()

    def status(self):
        cash,high,halted=self.db.execute('SELECT cash,high_water,halted FROM account WHERE id=1').fetchone()
        positions=[json.loads(p[0]) for p in self.db.execute('SELECT payload FROM positions ORDER BY market_slug')]
        opened=[p for p in positions if p['state']=='PAPER_OPEN']
        return dict(mode='PAPER',venue='Polymarket US',cash=cash,open_exposure=str(sum((amount(p['cost']) for p in opened),Decimal(0))),
                    high_water=high,halted_reason=halted,positions=positions,
                    realized_pnl=str(sum((Decimal(p['pnl']) for p in positions if p['state']=='PAPER_CLOSED'),Decimal(0))),
                    live_orders_enabled=False)

    def cycle(self,markets,predictions,quotes,now,kill_switch=False):
        config=self.config
        lookup={m['market_slug']:m for m in markets}
        if not math.isfinite(now):
            raise ValueError('Invalid observation time')
        decisions=[]
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.db.execute('SELECT observed_at FROM bot_snapshot WHERE id=1').fetchone()
            if previous and now<previous[0]:
                raise ValueError('Observation clock moved backwards')
            cash,high,halted=self.db.execute('SELECT cash,high_water,halted FROM account WHERE id=1').fetchone()
            cash,high=amount(cash),amount(high)
            positions={slug:json.loads(payload) for slug,payload in self.db.execute('SELECT market_slug,payload FROM positions')}
            # Only authoritative, already-known results close positions; even
            # during a kill switch, settlement/accounting continues.
            for slug,position in positions.items():
                m=lookup.get(slug)
                if position['state']!='PAPER_OPEN' or not m:
                    continue
                try:
                    final=verified(m,now)
                except (ValueError,TypeError,KeyError):
                    final=False
                if (m.get('contract_slug')!=position['contract_slug'] or m.get('asset')!=position['asset']
                        or m.get('duration_seconds')!=position['duration_seconds'] or not final):
                    continue
                try:
                    if (time_of(m['window_start'])!=position['window_start'] or time_of(m['window_end'])!=position['window_end']
                            or amount(m['official_price_to_beat'])!=amount(position['price_to_beat'])):
                        continue
                except (ValueError,KeyError,TypeError,ArithmeticError):
                    continue
                payout=amount(position['quantity']) if position['side']==m['official_winner'] else Decimal(0)
                cash+=payout
                position.update(state='PAPER_CLOSED',payout=str(payout),pnl=str(payout-amount(position['cost'])),closed_at=now)
                self.db.execute('UPDATE positions SET payload=? WHERE market_slug=?',(json.dumps(position),slug))
            opened=[p for p in positions.values() if p['state']=='PAPER_OPEN']
            exposure=sum((amount(p['cost']) for p in opened),Decimal(0))
            # Realized/cost-basis equity; NOT a live bid-marked portfolio value.
            equity=cash+exposure
            high=max(high,equity)
            if high>0 and (high-equity)/high>=amount(config.max_drawdown):
                halted='MAX_REALIZED_DRAWDOWN'
            today=datetime.fromtimestamp(now,timezone.utc).date()
            daily=sum((Decimal(p['pnl']) for p in positions.values() if p['state']=='PAPER_CLOSED'
                       and datetime.fromtimestamp(p['closed_at'],timezone.utc).date()==today),Decimal(0))
            candidates={}
            for prediction in predictions:
                if prediction.get('model_version')!=config.model_version:
                    continue
                try:
                    known=lookup.get(prediction.get('market_slug'))
                    if known and time_of(known['window_end'])<=now:
                        continue
                    when=time_of(prediction['recorded_at'])
                    if when>now:
                        continue
                    old=candidates.get(prediction['market_slug'])
                    if old is None or when>time_of(old['recorded_at']):
                        candidates[prediction['market_slug']]=prediction
                except (KeyError,TypeError,ValueError):
                    continue
            for slug,p in sorted(candidates.items()):
                metadata=lookup.get(slug,{})
                decision=dict(market_slug=slug,asset=metadata.get('asset'),duration_seconds=metadata.get('duration_seconds'),model_version=config.model_version,recorded_at=p['recorded_at'],action='SKIP')
                decisions.append(decision)
                try:
                    if kill_switch: raise ValueError('KILL_SWITCH')
                    if halted: raise ValueError(halted)
                    if daily<=-amount(config.max_daily_loss): raise ValueError('DAILY_LOSS_LIMIT')
                    if slug in positions: raise ValueError('ALREADY_TRADED_MARKET')
                    m=lookup[slug]
                    if (m['asset'],m['duration_seconds']) not in STREAMS: raise ValueError('UNSUPPORTED_STREAM')
                    start,end=time_of(m['window_start']),time_of(m['window_end'])
                    when=time_of(p['recorded_at'])
                    if end-start!=m['duration_seconds'] or not start<=when<=now<end: raise ValueError('MARKET_WINDOW')
                    if end-now<config.minimum_seconds_remaining: raise ValueError('TOO_CLOSE_TO_EXPIRY')
                    if now-when>config.max_prediction_age or not start<=time_of(p['source_timestamp'])<=when or now-time_of(p['source_timestamp'])>config.max_source_age: raise ValueError('STALE_OR_FUTURE_SIGNAL')
                    if not m.get('contract_slug') or amount(m.get('official_price_to_beat',0))<=0 or m.get('settlement_status')!='PENDING': raise ValueError('MARKET_NOT_READY')
                    up=amount(p['predicted_up_probability'])
                    if up>1 or up==Decimal('.5'): raise ValueError('NO_DIRECTION')
                    side='UP' if up>Decimal('.5') else 'DOWN'
                    if config.require_lean_alignment and p.get('lean_direction')!=side: raise ValueError('LEAN_DISAGREES')
                    score=historical_score(lookup,predictions,m,config.model_version,int((when-start)/(m['duration_seconds']/5)),now,config.max_source_age)
                    decision['history']=score
                    if score['markets']<config.minimum_settled_markets: raise ValueError('INSUFFICIENT_HISTORY')
                    if score['brier']>config.maximum_brier: raise ValueError('HISTORICAL_SCORE_GATE')
                    eligible=[q for q in quotes if q.get('market_slug')==slug and q.get('contract_slug')==m['contract_slug']
                              and q.get('side_mapping_verified') is True and q.get('side_mapping_evidence')
                              and q.get('source_name')=='Polymarket US'
                              and when<=time_of(q['captured_at'])<=now and now-time_of(q['captured_at'])<=config.max_quote_age]
                    if not eligible: raise ValueError('NO_FRESH_MAPPED_QUOTE')
                    q=min(eligible,key=lambda q:time_of(q['captured_at']))
                    ask,bid=amount(q[side.lower()+'_ask']),amount(q[side.lower()+'_bid'])
                    if not 0<ask<=1 or bid>ask or ask-bid>amount(config.maximum_spread): raise ValueError('SPREAD_OR_PRICE')
                    fee,slip=amount(config.fee_per_share),amount(config.slippage_per_share)
                    fill=ask+slip
                    cost_per_share=fill+fee
                    probability=up if side=='UP' else 1-up
                    edge=probability-cost_per_share
                    if fill>1 or edge<amount(config.minimum_edge): raise ValueError('NO_NET_EDGE')
                    depth=amount(q[side.lower()+'_ask_size'])
                    daily_capacity=amount(config.max_daily_loss)+daily-exposure
                    drawdown_capacity=high*amount(config.max_drawdown)-(high-equity)-exposure
                    budget=min(amount(config.max_trade_cost),cash,amount(config.max_exposure)-exposure,daily_capacity,drawdown_capacity)
                    quantity=min(depth,(budget/cost_per_share).to_integral_value(rounding=ROUND_FLOOR)).to_integral_value(rounding=ROUND_FLOOR)
                    if len(opened)>=config.max_open_positions or quantity<1: raise ValueError('RISK_OR_LIQUIDITY_LIMIT')
                    cost=quantity*cost_per_share
                    position=dict(market_slug=slug,contract_slug=m['contract_slug'],asset=m['asset'],duration_seconds=m['duration_seconds'],
                                  model_version=config.model_version,side=side,state='PAPER_OPEN',window_start=start,window_end=end,price_to_beat=str(amount(m['official_price_to_beat'])),quantity=str(quantity),entry_price=str(fill),
                                  cost=str(cost),fees=str(quantity*fee),opened_at=now,quote_at=q['captured_at'],signal_at=p['recorded_at'],
                                  edge=str(edge),simulated_only=True)
                    self.db.execute('INSERT INTO positions VALUES (?,?)',(slug,json.dumps(position)))
                    positions[slug]=position
                    opened.append(position)
                    cash-=cost
                    exposure+=cost
                    decision.update(action='PAPER_BUY',side=side,quantity=str(quantity),cost=str(cost))
                except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
                    decision['reason']=str(exc) if isinstance(exc,ValueError) else 'INVALID_INPUT'
                event=hashlib.sha256(json.dumps(decision,sort_keys=True).encode()).hexdigest()
                self.db.execute('INSERT OR IGNORE INTO decisions VALUES (?,?,?)',(event,now,json.dumps(decision,sort_keys=True)))
            self.db.execute('UPDATE account SET cash=?,high_water=?,halted=? WHERE id=1',(str(cash),str(high),halted))
            result=dict(observed_at=now,decisions=decisions,account=self.status(),configuration=asdict(config))
            self.db.execute('INSERT INTO bot_snapshot VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',(now,json.dumps(result,sort_keys=True)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return result
