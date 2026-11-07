"""Delayed, frozen-limit FOK paper spot execution using sampled Coinbase books."""
from dataclasses import dataclass,fields
from decimal import Decimal,ROUND_DOWN,ROUND_UP
import hashlib
import json
from coinbase_bot.core import Config,PaperBot
from coinbase_bot.market_data import positive,PRODUCTS


@dataclass(frozen=True)
class ObservedConfig(Config):
    execution_version: str='COINBASE_OBSERVED_LIMIT_V1'
    latency_seconds: int=2
    order_ttl_seconds: int=45
    participation: str='.25'
    fee_basis: str='ESTIMATED_0.6_PERCENT_PER_SIDE_ACCOUNT_TIER_NOT_CONNECTED'

    def validate(self):
        Config(**{f.name:getattr(self,f.name) for f in fields(Config)}).validate()
        if (self.execution_version!='COINBASE_OBSERVED_LIMIT_V1' or self.latency_seconds!=2
                or self.order_ttl_seconds!=45 or self.participation!='.25'
                or self.fee_rate!='0.006'
                or self.fee_basis!='ESTIMATED_0.6_PERCENT_PER_SIDE_ACCOUNT_TIER_NOT_CONNECTED'):
            raise ValueError('Use a new execution version for changed assumptions')
        return self


class ObservedBot(PaperBot):
    def __init__(self,path,config=None):
        super().__init__(path,config or ObservedConfig())
        self.db.execute('''CREATE TABLE IF NOT EXISTS execution_orders(
          id TEXT PRIMARY KEY,product TEXT,side TEXT,state TEXT,payload TEXT,result TEXT)''')
        self.db.commit()

    def pending(self,product,side):
        row=self.db.execute("SELECT payload FROM execution_orders WHERE product=? AND side=? AND state='PROPOSED'",(product,side)).fetchone()
        return json.loads(row[0]) if row else None

    def reserved_cash(self,except_product):
        return sum((Decimal(json.loads(p)['reserve']) for product,p in self.db.execute(
            "SELECT product,payload FROM execution_orders WHERE side='BUY' AND state='PROPOSED'") if product!=except_product),Decimal(0))

    def execute(self,source,side,quantity,now,reason=None):
        product=source['product_id'];cfg=self.config;metadata=source['metadata']
        if str(metadata.get('status','')).upper()!='ONLINE' or any(metadata.get(k) for k in ('cancel_only','post_only','auction_mode','is_disabled','view_only')):
            raise ValueError('PRODUCT_RESTRICTED')
        proposal=self.pending(product,side)
        if not proposal:
            tick=positive(metadata['quote_increment']);increment=positive(metadata['base_increment'])
            observed=positive(source['ask' if side=='BUY' else 'bid'])
            rounding=ROUND_DOWN if side=='BUY' else ROUND_UP
            limit=(observed*(1+positive(cfg.slippage_rate) if side=='BUY' else 1-positive(cfg.slippage_rate))/tick).to_integral_value(rounding=rounding)*tick
            if side=='BUY':
                quantity=min(quantity,(positive(source['ask_size'])*Decimal('.25')/increment).to_integral_value(rounding=ROUND_DOWN)*increment)
            if quantity<positive(metadata['base_min_size']) or quantity*limit<positive(metadata['quote_min_size']):
                raise ValueError('VISIBLE_SIZE_BELOW_MINIMUM')
            order=dict(product_id=product,side=side,order_configuration=dict(limit_limit_fok=dict(
                base_size=str(quantity),limit_price=str(limit))))
            proposal=dict(order=order,created_at=now,eligible_at=now+2,expires_at=now+45,
                          signal_candle_end=source['candles'][-1]['start']+60,
                          reserve=str(quantity*limit*(1+positive(cfg.fee_rate))) if side=='BUY' else '0',
                          reason=reason,fee_basis=cfg.fee_basis,fee_rate=cfg.fee_rate,initial_book_time=source['book_time'])
            identifier=hashlib.sha256(json.dumps(proposal,sort_keys=True).encode()).hexdigest()
            proposal['order']['client_order_id']=identifier
            self.db.execute('INSERT INTO execution_orders VALUES(?,?,?,?,?,NULL)',(identifier,product,side,'PROPOSED',json.dumps(proposal)))
            raise ValueError('ORDER_WAITING_FOR_POST_DELAY_BOOK')
        if now<proposal['eligible_at'] or source['book_time']<proposal['eligible_at']:
            raise ValueError('ORDER_WAITING_FOR_POST_DELAY_BOOK')
        if not proposal['eligible_at']<=source['book_time']<=source['observed_at']<=now:
            raise ValueError('INVALID_POST_DELAY_BOOK_TIME')
        from coinbase_bot.live import observed_order
        config=observed_order(proposal)['order_configuration']['limit_limit_fok']
        frozen_quantity=positive(config['base_size']);limit=positive(config['limit_price'])
        price=positive(source['ask' if side=='BUY' else 'bid']);size=positive(source['ask_size' if side=='BUY' else 'bid_size'])*Decimal('.25')
        valid=price<=limit if side=='BUY' else price>=limit
        if (not valid or size<frozen_quantity or frozen_quantity*price<positive(metadata['quote_min_size'])
                or frozen_quantity<positive(metadata['base_min_size'])
                or frozen_quantity%positive(metadata['base_increment'])!=0
                or limit%positive(metadata['quote_increment'])!=0):
            self.db.execute("UPDATE execution_orders SET state='REJECTED',result=? WHERE product=? AND side=? AND state='PROPOSED'",
                            (json.dumps(dict(reason='FOK_LIMIT_OR_DEPTH_UNFILLED',fee='0')),product,side))
            raise ValueError('FOK_LIMIT_OR_DEPTH_UNFILLED')
        # Fees are a clearly labeled rate estimate; no fake account-specific tier.
        fee=frozen_quantity*price*positive(proposal['fee_rate'])
        result=dict(quantity=str(frozen_quantity),price=str(price),fees=str(fee),book_time=source['book_time'],
                    executed_at=now,fee_basis=proposal['fee_basis'],simulated_only=True)
        self.db.execute("UPDATE execution_orders SET state='FILLED',result=? WHERE product=? AND side=? AND state='PROPOSED'",
                        (json.dumps(result),product,side))
        return price,frozen_quantity,fee

    def cycle(self,snapshots,now,kill_switch=False):
        previous=self.db.execute('SELECT observed_at FROM bot_snapshot WHERE id=1').fetchone()
        if previous and now<previous[0]: raise ValueError('Clock moved backwards')
        with self.db:
            for identifier,side,payload in self.db.execute("SELECT id,side,payload FROM execution_orders WHERE state='PROPOSED'").fetchall():
                p=json.loads(payload)
                if now>=p['expires_at'] or (kill_switch and side=='BUY'):
                    self.db.execute("UPDATE execution_orders SET state='CANCELLED',result=? WHERE id=?",
                                    (json.dumps(dict(reason='EXPIRED_OR_PAUSED',fee='0')),identifier))
        report=super().cycle(snapshots,now,kill_switch)
        report['operation_mode']='OBSERVED_LIMIT_PAPER'
        report['fee_basis']=self.config.fee_basis
        report['execution_assumptions']=['Two-second minimum delay; actual wait follows sampled-book cadence.',
            'Frozen limit, FOK, at most 25% of displayed best-level size. No partial fills or passive queue claims.',
            'Fee tier and fee precision are estimated until actual account data is connected.',
            'Spot strategy and risk checks unchanged; no leverage, no live orders.']
        report['order_states']=dict(self.db.execute('SELECT state,count(*) FROM execution_orders GROUP BY state'))
        report['recent_orders']=[dict(order=json.loads(p),state=state,result=json.loads(r) if r else None)
            for state,p,r in self.db.execute('SELECT state,payload,result FROM execution_orders ORDER BY rowid DESC LIMIT 30')]
        rows=[]
        for product in PRODUCTS:
            trades=[t for t in report['account']['trades'] if t['product_id']==product]
            fees=sum((Decimal(t.get('entry_fees','0'))+Decimal(t.get('exit_fees','0')) for t in trades),Decimal(0))
            net=sum((Decimal(t['pnl']) for t in trades),Decimal(0))
            rows.append(dict(product_id=product,closed_trades=len(trades),realized_net_pnl=str(net),estimated_fees=str(fees),
                             realized_gross_pnl=str(net+fees)))
        report['market_pnl']=rows
        # Bound API output, retain full histories in the ledger.
        report['account']['trades']=report['account']['trades'][-100:]
        with self.db: self.db.execute('UPDATE bot_snapshot SET payload=? WHERE id=1',(json.dumps(report),))
        return report
