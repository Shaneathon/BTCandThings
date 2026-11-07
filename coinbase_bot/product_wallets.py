"""Independent per-product paper wallets with history-preserving migration."""
import argparse
from dataclasses import dataclass,asdict
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import time
from coinbase_bot.market_data import PRODUCTS
from coinbase_bot.observed import ObservedBot,ObservedConfig
from coinbase_bot.fee_filter import FeeFilterBot,FeeFilterConfig


@dataclass(frozen=True)
class ProductConfig(ObservedConfig):
    initial_cash: str='250'
    max_exposure: str='50'
    max_daily_loss: str='25'
    product_id: str='BTC-USD'
    allocation_version: str='PRODUCT_ISOLATION_V1'

    def validate(self):
        super().validate()
        if self.product_id not in PRODUCTS or self.allocation_version!='PRODUCT_ISOLATION_V1':
            raise ValueError('Unknown isolated wallet')
        return self


@dataclass(frozen=True)
class ProductFeeConfig(FeeFilterConfig):
    initial_cash: str='250'
    max_exposure: str='50'
    max_daily_loss: str='25'
    product_id: str='BTC-USD'
    allocation_version: str='PRODUCT_ISOLATION_V1'

    def validate(self):
        super().validate()
        if self.product_id not in PRODUCTS or self.allocation_version!='PRODUCT_ISOLATION_V1':
            raise ValueError('Unknown isolated wallet')
        return self


class ProductScope:
    def __init__(self,path,config):
        super().__init__(path,config)
        self.db.execute('CREATE TABLE IF NOT EXISTS experiment_metadata(key TEXT PRIMARY KEY,value REAL)')
        for table in ('positions','trades'):
            if any(json.loads(row[0]).get('product_id')!=config.product_id for row in self.db.execute('SELECT payload FROM '+table)):
                raise ValueError('Foreign product in isolated ledger')
        self.db.commit()

    def execute(self,source,*args,**kwargs):
        if source.get('product_id')!=self.config.product_id: raise ValueError('WRONG_ISOLATED_WALLET_PRODUCT')
        return super().execute(source,*args,**kwargs)

    def cycle(self,snapshots,now,kill_switch=False):
        product=self.config.product_id
        report=super().cycle({product:snapshots[product]} if product in snapshots else {},now,kill_switch)
        source=snapshots.get(product,{})
        report['input_status']='FRESH' if (not source.get('error') and 0<=now-source.get('book_time',0)<=15 and 0<=now-source.get('observed_at',0)<=30) else 'UNAVAILABLE'
        report['selected_product']=product
        report['wallet_initial_allocation']=self.config.initial_cash
        report['market_pnl']=[r for r in report.get('market_pnl',[]) if r['product_id']==product]
        report['market_candles']={product:report.get('market_candles',{}).get(product,[])}
        report['decisions']=[d for d in report['decisions'] if d['product_id']==product]
        report['configuration']=asdict(self.config)
        reserve=sum((Decimal(json.loads(r[0])['reserve']) for r in self.db.execute(
            "SELECT payload FROM execution_orders WHERE side='BUY' AND state='PROPOSED'")),Decimal(0))
        report['account']['reserved_cash']=str(reserve)
        report['account']['available_cash']=str(Decimal(report['account']['cash'])-reserve)
        with self.db: self.db.execute('UPDATE bot_snapshot SET payload=? WHERE id=1',(json.dumps(report),))
        return report


class ProductBot(ProductScope,ObservedBot): pass
class ProductFeeBot(ProductScope,FeeFilterBot): pass


def open_bot(path,strategy):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        config=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
    return ProductFeeBot(path,ProductFeeConfig(**config)) if strategy=='fee-filter' else ProductBot(path,ProductConfig(**config))


def migrate(source,destination,strategy,now):
    """Caller stops writers first. Never writes the source; rejects overwrites."""
    destination=Path(destination)
    if destination.exists(): raise ValueError('Destination exists; preserve existing wallet history')
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('Source integrity check failed')
        cfg=json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
        cash,_,halted=db.execute('SELECT cash,high_water,halted FROM account WHERE id=1').fetchone()
        initial=Decimal(cfg['initial_cash'])/len(PRODUCTS)
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        metadata=list(db.execute('SELECT key,value FROM experiment_metadata')) if 'experiment_metadata' in tables else []
        destination.mkdir(parents=True,mode=0o700)
        total_cash=Decimal(0);summary=[]
        for product in PRODUCTS:
            values=dict(cfg,initial_cash=str(initial),max_exposure=str(Decimal(cfg['max_exposure'])/4),
                        max_daily_loss=str(Decimal(cfg['max_daily_loss'])/4),product_id=product,allocation_version='PRODUCT_ISOLATION_V1')
            values['max_position_cost']=str(min(Decimal(cfg['max_position_cost']),Decimal(values['max_exposure'])))
            config=ProductFeeConfig(**values) if strategy=='fee-filter' else ProductConfig(**values)
            target=destination/(product+'.sqlite')
            bot=ProductFeeBot(target,config) if strategy=='fee-filter' else ProductBot(target,config)
            try:
                with bot.db:
                    for table,column in [('market_candles','product_id'),('market_books','product_id'),('positions','product_id'),
                         ('trades','product_id'),('processed','product_id'),('decision_journal','product_id'),('execution_orders','product')]:
                        if table not in tables: continue
                        if table=='trades':
                            rows=[r for r in db.execute('SELECT * FROM trades') if json.loads(r[-1])['product_id']==product]
                        else:
                            rows=db.execute('SELECT * FROM '+table+' WHERE '+column+'=?',(product,)).fetchall()
                        if rows:
                            count=len(rows[0]);bot.db.executemany('INSERT OR REPLACE INTO '+table+' VALUES('+','.join('?' for _ in range(count))+')',rows)
                    positions=[json.loads(r[0]) for r in bot.db.execute('SELECT payload FROM positions')]
                    trades=[json.loads(r[0]) for r in bot.db.execute('SELECT payload FROM trades')]
                    pnl=sum((Decimal(t['pnl']) for t in trades),Decimal(0))
                    cost=sum((Decimal(p['cost']) for p in positions),Decimal(0))
                    allocated=initial+pnl-cost
                    if allocated<0: raise ValueError('Product allocation cannot fund inherited history/position')
                    running=initial;high=initial
                    for t in sorted(trades,key=lambda t:t['closed_at']):
                        running+=Decimal(t['pnl']);high=max(high,running)
                    bot.db.execute('UPDATE account SET cash=?,high_water=?,halted=? WHERE id=1',(str(allocated),str(high),halted))
                    # Unsubmitted paper BUYs are cancelled without a fee when
                    # funding limits change. Existing SELLs/holdings are retained.
                    bot.db.execute("UPDATE execution_orders SET state='CANCELLED',result=? WHERE side='BUY' AND state='PROPOSED'",
                        (json.dumps(dict(reason='PRODUCT_WALLET_MIGRATION',fee='0')),))
                    bot.db.executemany('INSERT OR REPLACE INTO experiment_metadata VALUES(?,?)',metadata)
                    bot.db.execute("INSERT OR REPLACE INTO experiment_metadata VALUES('wallet_isolation_started_at',?)",(now,))
                bot.cycle({},now,kill_switch=True)
                total_cash+=allocated
                summary.append(dict(product=product,initial_allocation=str(initial),cash=str(allocated),
                                    realized_pnl=str(pnl),open_cost=str(cost),closed_trades=len(trades)))
            finally: bot.close()
        if abs(total_cash-Decimal(cash))>Decimal('.00000001'): raise ValueError('Migrated cash does not reconcile with source')
    return summary


def aggregate(reports,strategy,now,input_error=None):
    accounts=[r['account'] for r in reports.values()]
    total=lambda field:str(sum((Decimal(a.get(field,'0')) for a in accounts),Decimal(0)))
    ready=sum(r.get('input_status')=='FRESH' for r in reports.values())
    return dict(observed_at=now,operation_mode='PRODUCT_WALLETS_PAPER',strategy=strategy,
                input_status='FRESH' if ready==len(PRODUCTS) else 'PARTIAL' if ready else 'UNAVAILABLE',
                account=dict(mode='PAPER',venue='Coinbase Advanced',live_orders_enabled=False,cash=total('cash'),
                    open_exposure=total('open_exposure'),realized_pnl=total('realized_pnl')),
                product_wallets=reports,input_error=input_error,
                funding_note='Separate allocations, cash and risk limits; no cross-product borrowing. Existing per-product history carried forward.')


def enrich_snapshot(path):
    from trading_bot.server import snapshot
    from coinbase_bot.comparison import compare
    result=snapshot(path);root=Path(path).parent
    result['product_comparisons']={}
    for product in PRODUCTS:
        baseline=root/'products'/'baseline'/(product+'.sqlite')
        challenger=root/'products'/'fee-filter'/(product+'.sqlite')
        if challenger.exists():
            try: result['product_comparisons'][product]=compare(baseline,challenger)
            except Exception as error: result['product_comparisons'][product]=dict(error=type(error).__name__)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('migrate','watch'))
    p.add_argument('--strategy',choices=('baseline','fee-filter'),required=True)
    p.add_argument('--state',type=Path,required=True)
    p.add_argument('--source',type=Path)
    p.add_argument('--status',type=Path)
    p.add_argument('--kill-file',type=Path)
    args=p.parse_args()
    if args.command=='migrate':
        print(json.dumps(migrate(args.source,args.state,args.strategy,time.time()),indent=2));return
    from coinbase_tracker.client import fetch,bot_inputs
    import os
    bots={product:open_bot(args.state/(product+'.sqlite'),args.strategy) for product in PRODUCTS}
    db=sqlite3.connect(args.status,timeout=15)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS bot_snapshot(id INTEGER PRIMARY KEY,observed_at REAL,payload TEXT)')
    try:
        while True:
            error=None
            try: data=bot_inputs(fetch('http://127.0.0.1:8767/status',os.environ.get('COIN_READ_TOKEN','')))
            except (OSError,ValueError,TypeError,KeyError) as exc: data={};error='INPUT_'+type(exc).__name__
            now=time.time();reports={}
            for product,bot in bots.items(): reports[product]=bot.cycle(data,now,kill_switch=args.kill_file.exists())
            report=aggregate(reports,args.strategy,time.time(),error)
            with db: db.execute('INSERT INTO bot_snapshot VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',(report['observed_at'],json.dumps(report)))
            print(json.dumps(dict(mode=report['operation_mode'],strategy=args.strategy,input_error=error,live_orders=False)),flush=True)
            time.sleep(5)
    finally:
        db.close()
        for bot in bots.values(): bot.close()



def audit_products(root,now):
    from trading_bot.verify_runtime import cbot_report
    from trading_bot.server import snapshot
    root=Path(root);report=snapshot(root/'product-baseline.sqlite')
    wallets={p:cbot_report(root/'products'/'baseline'/(p+'.sqlite'),now) for p in PRODUCTS}
    return dict(mode=report.get('operation_mode'),status_age_seconds=round(now-report.get('observed_at',0),1),
                live_orders_enabled=report['account']['live_orders_enabled'],cash=report['account']['cash'],
                open_cost=report['account']['open_exposure'],realized_pnl=report['account']['realized_pnl'],
                accounting_ok=all(v['accounting_ok'] for v in wallets.values()),product_wallets=wallets)

if __name__=='__main__': main()
