"""Separate Coinbase spot paper wallet. Decimal accounting, no orders/network."""
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from decimal import Decimal,ROUND_FLOOR
import json
import sqlite3
from coinbase_bot.market_data import PRODUCTS,positive,momentum


@dataclass(frozen=True)
class Config:
    initial_cash: str='1000'
    max_position_cost: str='50'
    max_exposure: str='200'
    max_daily_loss: str='100'
    max_drawdown: str='0.20'
    fee_rate: str='0.006'
    slippage_rate: str='0.0005'
    maximum_spread_fraction: str='0.003'
    stop_loss_fraction: str='0.02'
    take_profit_fraction: str='0.04'
    cooldown_seconds: int=300

    def validate(self):
        for key,value in asdict(self).items():
            if key!='cooldown_seconds': positive(value)
        for key in ('fee_rate','slippage_rate','maximum_spread_fraction','stop_loss_fraction','take_profit_fraction','max_drawdown'):
            if positive(getattr(self,key))>=1: raise ValueError('Fractions must be below one')
        if not positive(self.max_position_cost)<=positive(self.max_exposure)<=positive(self.initial_cash): raise ValueError('Invalid position limits')
        if type(self.cooldown_seconds) is not int or self.cooldown_seconds<0: raise ValueError('Invalid cooldown')
        return self


class PaperBot:
    def __init__(self,path,config=None):
        self.config=(config or Config()).validate()
        from trading_bot.ledger_guard import check_existing
        check_existing(path,json.dumps(asdict(self.config),sort_keys=True))
        self.db=sqlite3.connect(path,timeout=15)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY,cash TEXT,high_water TEXT,halted TEXT);
          CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY,payload TEXT);
          CREATE TABLE IF NOT EXISTS market_candles (product_id TEXT,start INTEGER,payload TEXT,PRIMARY KEY(product_id,start));
          CREATE TABLE IF NOT EXISTS market_books (product_id TEXT,observed_at REAL,payload TEXT,PRIMARY KEY(product_id,observed_at));
          CREATE TABLE IF NOT EXISTS positions (product_id TEXT PRIMARY KEY,payload TEXT);
          CREATE TABLE IF NOT EXISTS trades (trade_id TEXT PRIMARY KEY,payload TEXT);
          CREATE TABLE IF NOT EXISTS processed (product_id TEXT PRIMARY KEY,candle_end REAL,last_exit REAL);
          CREATE TABLE IF NOT EXISTS bot_snapshot (id INTEGER PRIMARY KEY,observed_at REAL,payload TEXT);
          CREATE TABLE IF NOT EXISTS decision_journal (product_id TEXT,observed_at REAL,payload TEXT,PRIMARY KEY(product_id,observed_at));
        ''')
        value=json.dumps(asdict(self.config),sort_keys=True)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO settings VALUES (1,?)',(value,))
            if self.db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0]!=value:
                raise ValueError('Use a separate experiment ledger when changing configuration')
            self.db.execute('INSERT OR IGNORE INTO account VALUES (1,?,?,NULL)',(self.config.initial_cash,self.config.initial_cash))

    def close(self): self.db.close()

    def pending(self,product,side): return None

    def reserved_cash(self,except_product): return Decimal(0)

    def execute(self,source,side,quantity,now,reason=None):
        price=(positive(source['ask'])*(1+positive(self.config.slippage_rate)) if side=='BUY'
               else positive(source['bid'])*(1-positive(self.config.slippage_rate)))
        return price,quantity,quantity*price*positive(self.config.fee_rate)

    def cycle(self,snapshots,now,kill_switch=False):
        cfg=self.config
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT observed_at FROM bot_snapshot WHERE id=1').fetchone()
            if old and now<old[0]: raise ValueError('Clock moved backwards')
            cash,high,halted=self.db.execute('SELECT cash,high_water,halted FROM account WHERE id=1').fetchone()
            cash,high=positive(cash,zero=True),positive(high)
            positions={p:json.loads(r) for p,r in self.db.execute('SELECT product_id,payload FROM positions')}
            trades=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM trades')]
            today=datetime.fromtimestamp(now,timezone.utc).date()
            daily=sum((Decimal(t['pnl']) for t in trades if datetime.fromtimestamp(t['closed_at'],timezone.utc).date()==today),Decimal(0))
            exposure=sum((positive(p['cost']) for p in positions.values()),Decimal(0))
            high=max(high,cash+exposure)
            decisions=[]
            for product in PRODUCTS:
                decision=dict(product_id=product,action='WAIT')
                decisions.append(decision)
                try:
                    source=snapshots.get(product,{})
                    if source.get('error'): raise ValueError('FEED_UNAVAILABLE')
                    if source.get('product_id')!=product: raise ValueError('WRONG_PRODUCT')
                    if not 0<=now-source['book_time']<=15 or not 0<=now-source['observed_at']<=30: raise ValueError('STALE_BOOK')
                    metadata=source['metadata']
                    if (metadata.get('product_id')!=product or metadata.get('product_type')!='SPOT'
                            or metadata.get('base_currency_id')!=product.split('-')[0] or metadata.get('quote_currency_id')!='USD'
                            or metadata.get('trading_disabled') is not False): raise ValueError('PRODUCT_NOT_READY')
                    bars=source['candles']
                    if len(bars)<60 or any(b['start']-a['start']!=60 for a,b in zip(bars,bars[1:])): raise ValueError('INVALID_CANDLE_HISTORY')
                    checked=[]
                    for bar in bars:
                        if bar['start']%60 or bar['start']+60>now: raise ValueError('INCOMPLETE_CANDLE')
                        o,h,l,c=(positive(bar[k]) for k in ('open','high','low','close'))
                        positive(bar['volume'],zero=True)
                        if h<max(o,l,c) or l>min(o,h,c): raise ValueError('INVALID_OHLC')
                        checked.append((product,bar['start'],json.dumps({k:bar[k] for k in ('start','open','high','low','close','volume')})))
                    self.db.executemany('INSERT INTO market_candles VALUES (?,?,?) ON CONFLICT(product_id,start) DO UPDATE SET payload=excluded.payload',checked)
                    self.db.execute('INSERT OR IGNORE INTO market_books VALUES (?,?,?)',(product,source['book_time'],json.dumps({k:source[k] for k in ('product_id','book_time','bid','ask','bid_size','ask_size')})))
                    signal=momentum(source)
                    if not 0<=now-signal['candle_end']<=120: raise ValueError('STALE_SIGNAL')
                    decision['signal']=signal
                    bid,ask=positive(source['bid']),positive(source['ask'])
                    if bid>ask: raise ValueError('CROSSED_BOOK')
                    prior=self.db.execute('SELECT candle_end,last_exit FROM processed WHERE product_id=?',(product,)).fetchone()
                    last_exit=prior[1] if prior else None
                    position=positions.get(product)
                    # Exits remain available during the entry kill switch.
                    if position:
                        entry=positive(position['entry_price'])
                        reason=('STOP_LOSS' if bid<=entry*(1-positive(cfg.stop_loss_fraction)) else
                                'TAKE_PROFIT' if bid>=entry*(1+positive(cfg.take_profit_fraction)) else
                                'TREND_EXIT' if signal['direction']=='SELL' else None)
                        queued=self.pending(product,'SELL')
                        reason=reason or (queued.get('reason') if queued else None)
                        if not reason: raise ValueError('HOLDING_SPOT')
                        quantity=positive(position['quantity'])
                        if positive(source['bid_size'])<quantity: raise ValueError('INSUFFICIENT_EXIT_DEPTH')
                        price,quantity,exit_fee=self.execute(source,'SELL',quantity,now,reason=reason)
                        proceeds=quantity*price-exit_fee
                        pnl=proceeds-positive(position['cost'])
                        cash+=proceeds; exposure-=positive(position['cost']); daily+=pnl
                        trade={**position,'closed_at':now,'exit_price':str(price),'proceeds':str(proceeds),'pnl':str(pnl),'exit_reason':reason,'exit_fees':str(exit_fee)}
                        trade_id=product+':'+str(position['opened_at'])
                        self.db.execute('INSERT INTO trades VALUES (?,?)',(trade_id,json.dumps(trade)))
                        self.db.execute('DELETE FROM positions WHERE product_id=?',(product,))
                        self.db.execute('INSERT INTO processed VALUES (?,?,?) ON CONFLICT(product_id) DO UPDATE SET candle_end=excluded.candle_end,last_exit=excluded.last_exit',(product,signal['candle_end'],now))
                        positions.pop(product)
                        decision.update(action='PAPER_SELL',reason=reason,pnl=str(pnl))
                        continue
                    if kill_switch: raise ValueError('KILL_SWITCH')
                    equity=cash+exposure
                    high=max(high,equity)
                    if (high-equity)/high>=positive(cfg.max_drawdown): halted='MAX_REALIZED_DRAWDOWN'
                    if halted: raise ValueError(halted)
                    if daily<=-positive(cfg.max_daily_loss): raise ValueError('DAILY_LOSS_LIMIT')
                    if prior and prior[0]>=signal['candle_end'] and not self.pending(product,'BUY'): raise ValueError('ALREADY_PROCESSED_CANDLE')
                    if last_exit is not None and now-last_exit<cfg.cooldown_seconds: raise ValueError('COOLDOWN')
                    self.db.execute('INSERT INTO processed VALUES (?,?,NULL) ON CONFLICT(product_id) DO UPDATE SET candle_end=excluded.candle_end',(product,signal['candle_end']))
                    if signal['direction']!='BUY' and not self.pending(product,'BUY'): raise ValueError('NO_BUY_TREND')
                    if (ask-bid)/ask>positive(cfg.maximum_spread_fraction): raise ValueError('WIDE_SPREAD')
                    metadata=source['metadata']
                    if metadata.get('product_id')!=product or metadata.get('product_type')!='SPOT' or metadata.get('trading_disabled') is not False: raise ValueError('PRODUCT_NOT_READY')
                    fill=ask*(1+positive(cfg.slippage_rate))
                    unit_cost=fill*(1+positive(cfg.fee_rate))
                    reserve=self.reserved_cash(product)
                    capacity=min(positive(cfg.max_position_cost),cash-reserve,positive(cfg.max_exposure)-exposure-reserve,
                                 positive(cfg.max_daily_loss)+daily-exposure-reserve,
                                 high*positive(cfg.max_drawdown)-(high-equity)-exposure-reserve)
                    if metadata.get('quote_max_size'):
                        capacity=min(capacity,positive(metadata['quote_max_size'])*(1+positive(cfg.fee_rate)))
                    increment=positive(metadata['base_increment'])
                    quantity=(min(positive(source['ask_size']),capacity/unit_cost)/increment).to_integral_value(rounding=ROUND_FLOOR)*increment
                    if metadata.get('base_max_size'):
                        quantity=min(quantity,(positive(metadata['base_max_size'])/increment).to_integral_value(rounding=ROUND_FLOOR)*increment)
                    if quantity<positive(metadata['base_min_size']) or quantity*fill<positive(metadata['quote_min_size']): raise ValueError('MINIMUM_SIZE_OR_RISK')
                    fill,quantity,entry_fee=self.execute(source,'BUY',quantity,now)
                    cost=quantity*fill+entry_fee
                    position=dict(product_id=product,quantity=str(quantity),entry_price=str(fill),cost=str(cost),entry_fees=str(entry_fee),opened_at=now,simulated_only=True)
                    self.db.execute('INSERT INTO positions VALUES (?,?)',(product,json.dumps(position)))
                    positions[product]=position
                    cash-=cost; exposure+=cost
                    decision.update(action='PAPER_BUY',quantity=str(quantity),cost=str(cost))
                except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
                    decision['reason']=str(exc) if isinstance(exc,ValueError) else 'INVALID_INPUT'
            equity=cash+exposure
            high=max(high,equity)
            if (high-equity)/high>=positive(cfg.max_drawdown): halted='MAX_REALIZED_DRAWDOWN'
            self.db.execute('UPDATE account SET cash=?,high_water=?,halted=? WHERE id=1',(str(cash),str(high),halted))
            closed=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM trades')]
            self.db.executemany('INSERT OR IGNORE INTO decision_journal VALUES (?,?,?)',
                               [(d['product_id'],now,json.dumps(d)) for d in decisions])
            chart_data={p:[json.loads(row[0]) for row in self.db.execute('SELECT payload FROM market_candles WHERE product_id=? ORDER BY start DESC LIMIT 60',(p,))][::-1] for p in PRODUCTS}
            result=dict(observed_at=now,configuration=asdict(cfg),decisions=decisions,market_candles=chart_data,
                        account=dict(mode='PAPER',venue='Coinbase Advanced',cash=str(cash),open_exposure=str(exposure),positions=list(positions.values()),
                            realized_pnl=str(sum((Decimal(t['pnl']) for t in closed),Decimal(0))),trades=closed,
                            halted_reason=halted,live_orders_enabled=False))
            self.db.execute('INSERT INTO bot_snapshot VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',(now,json.dumps(result)))
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
