"""Forward-only BTC directional experiment. Fixed assumed prices, never orders.

This is NOT an executable-quote backtest or a profitability estimate. It does
not infer Yes/No mapping or fabricate exchange liquidity. Two separate wallets
measure model directions under the same explicitly hypothetical cost model.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from trading_bot.core import Config, PaperBot, amount, time_of, verified

MODELS = {'Champion': 'Pixel V13.5 Headless Baseline',
          'Challenger B': 'Challenger B Volatility V1'}


@dataclass(frozen=True)
class SandboxConfig(Config):
    experiment: str = 'BTC_DIRECTIONAL_FIXED_50C_V1'
    minimum_edge: str = '0.03'
    max_open_positions: int = 1
    max_exposure: str = '10'
    require_lean_alignment: bool = False

    def validate(self):
        super().validate()
        if amount(self.fee_per_share)!=Decimal('.01') or amount(self.slippage_per_share)!=Decimal('.01') or self.max_open_positions!=1:
            raise ValueError('This experiment version requires fixed 1c fee/slippage and one position; use a new version for changed assumptions')
        return self


@dataclass(frozen=True)
class MarketSandboxConfig(SandboxConfig):
    experiment: str = 'MULTI_ASSET_DIRECTIONAL_FIXED_50C_V1'
    asset: str = 'BTC'
    duration_seconds: int = 900


MARKET_STREAMS=[(asset,duration) for asset in ('BTC','ETH','XRP','SOL') for duration in (300,900)]+[('GOLD',900),('SILVER',900)]
RESEARCH_MODEL='Multi-asset spot baseline research V1'


class Sandbox(PaperBot):
    def cycle(self, markets, predictions, now, enabled=True, available_at=None):
        if not math.isfinite(now):
            raise ValueError('Invalid observation time')
        asset=getattr(self.config,'asset','BTC')
        duration=getattr(self.config,'duration_seconds',900)
        if (asset,duration) not in MARKET_STREAMS: raise ValueError('Unsupported market stream')
        lookup = {m['market_slug']: m for m in markets if m.get('asset') == asset and m.get('duration_seconds') == duration}
        decisions = []
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT observed_at FROM bot_snapshot WHERE id=1').fetchone()
            if old and now < old[0]:
                raise ValueError('Clock moved backwards')
            cash, high, halted = self.db.execute('SELECT cash,high_water,halted FROM account WHERE id=1').fetchone()
            cash, high = amount(cash), amount(high)
            positions = {slug:json.loads(p) for slug,p in self.db.execute('SELECT market_slug,payload FROM positions')}
            for slug, p in positions.items():
                m = lookup.get(slug)
                if p['state'] != 'PAPER_OPEN' or not m or not verified(m, now):
                    continue
                if (m.get('contract_slug') != p['contract_slug'] or time_of(m['window_start']) != p['window_start']
                        or time_of(m['window_end']) != p['window_end']
                        or amount(m.get('official_price_to_beat',0)) != amount(p['price_to_beat'])):
                    continue
                payout = amount(p['quantity']) if m['official_winner'] == p['side'] else Decimal(0)
                cash += payout
                p.update(state='PAPER_CLOSED', settled_at=now, official_winner=m['official_winner'],
                         payout=str(payout), pnl=str(payout-amount(p['cost'])))
                self.db.execute('UPDATE positions SET payload=? WHERE market_slug=?',(json.dumps(p),slug))
            opened = [p for p in positions.values() if p['state']=='PAPER_OPEN']
            exposure = sum((amount(p['cost']) for p in opened),Decimal(0))
            equity = cash + exposure
            high = max(high,equity)
            if high-equity >= high*amount(self.config.max_drawdown):
                halted = halted or 'DRAWDOWN_LIMIT'
            day = datetime.fromtimestamp(now,timezone.utc).date()
            daily = sum((Decimal(p['pnl']) for p in positions.values() if p['state']=='PAPER_CLOSED'
                         and datetime.fromtimestamp(p['settled_at'],timezone.utc).date()==day),Decimal(0))
            latest = {}
            for prediction in predictions:
                if prediction.get('model_version') != self.config.model_version:
                    continue
                slug = prediction.get('market_slug')
                stamp = time_of(prediction['recorded_at'])
                if stamp <= now and (slug not in latest or stamp > time_of(latest[slug]['recorded_at'])):
                    latest[slug] = prediction
            for slug,prediction in latest.items():
                m = lookup.get(slug)
                if not m or time_of(m['window_end']) <= now:
                    continue
                decision = dict(market_slug=slug,model_version=self.config.model_version,asset=asset,
                                duration_seconds=duration,action='SKIP',observed_at=now)
                try:
                    if not enabled: raise ValueError('PAUSED_OR_STALE_INPUT')
                    if halted: raise ValueError(halted)
                    if slug in positions: raise ValueError('ALREADY_ENTERED')
                    start,end = time_of(m['window_start']),time_of(m['window_end'])
                    stamp = time_of(prediction['recorded_at'])
                    if not start <= stamp <= now < end or end-start != duration: raise ValueError('MARKET_WINDOW')
                    if not 30 <= end-now <= 90: raise ValueError('WAIT_FOR_FINAL_90_SECONDS')
                    if not 0 <= now-stamp <= 90: raise ValueError('STALE_PREDICTION')
                    if isinstance(self.config,MarketSandboxConfig):
                        source=time_of(prediction['source_timestamp'])
                        if not start<=source<=stamp or not 0<=now-source<=120: raise ValueError('STALE_RESEARCH_SOURCE')
                    if available_at is None or not stamp <= available_at <= now: raise ValueError('AVAILABILITY_UNVERIFIED')
                    if m.get('settlement_status') != 'PENDING' or not m.get('contract_slug') or amount(m.get('official_price_to_beat',0))<=0: raise ValueError('MARKET_NOT_READY')
                    probability = amount(prediction['predicted_up_probability'])
                    if probability>1 or probability==Decimal('.5'): raise ValueError('NO_DIRECTION')
                    side = 'UP' if probability>Decimal('.5') else 'DOWN'
                    confidence = probability if side=='UP' else 1-probability
                    # An assumed 50c reference plus 1c slippage and 1c fee.
                    unit_cost = Decimal('.52')
                    if confidence-unit_cost < amount(self.config.minimum_edge): raise ValueError('BELOW_HYPOTHETICAL_THRESHOLD')
                    budget = min(amount(self.config.max_trade_cost),cash,
                                 amount(self.config.max_exposure)-exposure,
                                 amount(self.config.max_daily_loss)+daily-exposure,
                                 high*amount(self.config.max_drawdown)-(high-equity)-exposure)
                    quantity = (budget/unit_cost).to_integral_value(rounding=ROUND_FLOOR)
                    if len(opened)>=1 or quantity<1: raise ValueError('RISK_LIMIT')
                    cost = quantity*unit_cost
                    position = dict(market_slug=slug,contract_slug=m['contract_slug'],asset=asset,duration_seconds=duration,
                        model_version=self.config.model_version,state='PAPER_OPEN',side=side,quantity=str(quantity),
                        entry_price='0.51',reference_price='0.50',price_basis='HYPOTHETICAL_FIXED_50C',
                        liquidity_verified=False,fees=str(quantity*Decimal('.01')),cost=str(cost),opened_at=now,
                        window_start=start,window_end=end,price_to_beat=str(m['official_price_to_beat']),
                        signal_at=prediction['recorded_at'],signal_available_at=available_at,
                        predicted_up_probability=str(probability),simulated_only=True)
                    self.db.execute('INSERT INTO positions VALUES (?,?)',(slug,json.dumps(position)))
                    positions[slug]=position
                    opened.append(position)
                    exposure += cost
                    cash -= cost
                    decision.update(action='HYPOTHETICAL_ENTRY',reason='FIXED_PRICE_DIRECTIONAL_EXPERIMENT',side=side,cost=str(cost))
                except (ValueError,KeyError,TypeError,ArithmeticError) as error:
                    decision['reason']=str(error) if isinstance(error,ValueError) else 'INVALID_INPUT'
                decisions.append(decision)
                event=slug+'|'+decision['action']+'|'+decision['reason']
                self.db.execute('INSERT OR IGNORE INTO decisions VALUES (?,?,?)',(event,now,json.dumps(decision)))
            self.db.execute('UPDATE account SET cash=?,high_water=?,halted=? WHERE id=1',(str(cash),str(high),halted))
            account=self.status()
            all_positions=account['positions']
            all_closed=[p for p in all_positions if p['state']=='PAPER_CLOSED']
            account.update(settled_experiments_total=len(all_closed),
                           losses_total=sum(Decimal(p['pnl'])<0 for p in all_closed),
                           position_count=len(all_positions))
            from trading_bot.market_pnl import summarize
            account['market_pnl']=summarize(all_positions,streams=[(asset,duration)])
            # Preserve the complete ledger on disk; bound the private API response.
            account['positions']=sorted(all_positions,key=lambda p:p['opened_at'])[-100:]
            result=dict(observed_at=now,account=account,configuration=asdict(self.config),decisions=decisions,
                        operation_mode='DIRECTIONAL_SANDBOX',executable_quote_fills_enabled=False)
            self.db.execute('INSERT INTO bot_snapshot VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',
                            (now,json.dumps(result)))
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise


def export(source, output, group, all_markets=False, execution_evidence=False, execution_ledger=Path('/var/lib/pbot/observed-v1.sqlite')):
    now = time.time()
    start = int(now)//900*900
    slug = 'btc-updown-15m-'+datetime.fromtimestamp(start,timezone.utc).strftime('%Y-%m-%d-%H%M')+'z'
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        market_rows=(json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind='market'"))
        if execution_evidence:
            from trading_bot.input_packet import compact_markets,required_markets
            markets=compact_markets(market_rows,now,required_markets(execution_ledger))
        else:
            markets=list(market_rows)
        research=[]
        if all_markets:
            cutoff=datetime.fromtimestamp(now-180,timezone.utc).isoformat()
            research=[json.loads(row[0]) for row in db.execute('SELECT payload FROM research_snapshots WHERE recorded_at>=?',(cutoff,))]
    if not all_markets: markets=[m for m in markets if m.get('asset')=='BTC' and m.get('duration_seconds')==900]
    base=os.environ['SUPABASE_URL'].strip().rstrip('/')
    key=os.environ['SUPABASE_KEY'].strip()
    if not base.startswith('https://'): raise ValueError('HTTPS required')
    headers={'apikey':key}
    if not key.startswith('sb_secret_'): headers['Authorization']='Bearer '+key
    predictions=[]
    feed_errors=[]
    for table, model in [('btc_predictions',MODELS['Champion']),('btc_challenger_predictions',MODELS['Challenger B'])]:
        query=urlencode(dict(select='market_slug,recorded_at,predicted_up_probability,model_version',
                             market_slug='eq.'+slug,model_version='eq.'+model,
                             recorded_at='lte.'+datetime.fromtimestamp(now,timezone.utc).isoformat(),
                             order='recorded_at.desc',limit=1))
        try:
            with urlopen(Request(base+'/rest/v1/'+table+'?'+query,headers=headers,method='GET'),timeout=10) as response:
                rows=json.load(response)
        except Exception as error:
            if all_markets:
                feed_errors.append(dict(table=table,error=type(error).__name__,http_status=getattr(error,'code',None)))
                continue
            raise RuntimeError('Prediction feed unavailable: '+type(error).__name__) from None
        if not isinstance(rows,list): raise ValueError('Prediction response invalid')
        if any(row.get('market_slug')!=slug or row.get('model_version')!=model for row in rows):
            raise ValueError('Prediction identity mismatch')
        predictions.extend(rows)
    data=dict(exported_at=time.time(),markets=markets,predictions=predictions+research,requested_market=slug,feed_errors=feed_errors)
    if execution_evidence:
        from trading_bot.provider import evidence_packet
        data['execution_evidence']=evidence_packet(source,now=now)
    from trading_bot.input_packet import encode_packet
    encoded=encode_packet(data) if execution_evidence else json.dumps(data,allow_nan=False).encode()
    fd,temporary=tempfile.mkstemp(dir=Path(output).parent,prefix='.sandbox-')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        os.chown(temporary,0,group);os.chmod(temporary,0o640)
        os.replace(temporary,output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('Public BTC control predictions:',len(predictions),'| local research snapshots:',len(research),'| feed errors:',len(feed_errors))


def run_cycle(bots, data, now, paused=False):
    fresh=0<=now-data['exported_at']<=45
    predictions=data['predictions']
    # Both signals must be available for the same market before either enters.
    slugs={model:{p.get('market_slug') for p in predictions if p.get('model_version')==model
                  and 0<=now-time_of(p['recorded_at'])<=90} for model in MODELS.values()}
    shared=set.intersection(*slugs.values())
    predictions=[p for p in predictions if p.get('market_slug') in shared]
    reports={name:bot.cycle(data['markets'],predictions,now,enabled=fresh and not paused,
                            available_at=data['exported_at']) for name,bot in bots.items()}
    reviews={}
    for name,report in reports.items():
        closed=[p for p in report['account']['positions'] if p['state']=='PAPER_CLOSED']
        losses=[p for p in closed if Decimal(p['pnl'])<0]
        flagged=[]
        for p in losses:
            probability=Decimal(p['predicted_up_probability'])
            confidence=probability if p['side']=='UP' else 1-probability
            flagged.append(dict(market_slug=p['market_slug'],confidence=float(confidence),
                                classification='HIGH_CONFIDENCE_LOSS' if confidence>=Decimal('.9') else 'DIRECTIONAL_LOSS',
                                note='Outcome alone does not establish an entry mistake; prices and liquidity were hypothetical.'))
        total=report['account']['settled_experiments_total']
        total_losses=report['account']['losses_total']
        reviews[name]=dict(settled=total,losses=total_losses,wins=total-total_losses,
                           recent_loss_reviews=flagged[-20:],
                           next_action='Collect more forward observations; compare versioned entry-time and confidence rules.',
                           automatic_rule_changes=False,
                           reason='Keep baseline frozen; new rule versions need separate ledgers and forward validation.')
    return dict(observed_at=now,operation_mode='DIRECTIONAL_SANDBOX',
                input_status='FRESH' if fresh else 'STALE',common_signal_markets=len(shared),
                new_fixed_price_entries_paused=paused,
                account=dict(mode='PAPER',venue='Polymarket US',live_orders_enabled=False),portfolios=reports,
                price_assumption='Fixed hypothetical 50c + 1c slippage + 1c fee per share; liquidity unverified.',
                executable_quote_fills_enabled=False,automatic_reviews=reviews,feed_errors=data.get('feed_errors',[]))


def run_market_cycles(bots,data,now,paused=False):
    fresh=0<=now-data['exported_at']<=45
    reports={}
    for name,bot in bots.items():
        asset,duration=bot.config.asset,bot.config.duration_seconds
        current={m['market_slug'] for m in data['markets'] if m.get('asset')==asset
                 and m.get('duration_seconds')==duration and time_of(m['window_start'])<=now<time_of(m['window_end'])}
        predictions=[p for p in data['predictions'] if p.get('market_slug') in current
                     and p.get('model_version')==RESEARCH_MODEL and 0<=now-time_of(p['recorded_at'])<=90]
        report=bot.cycle(data['markets'],predictions,now,enabled=fresh and not paused,
                         available_at=data['exported_at'])
        report['stream']=name
        report['coverage_status']=('PAUSED' if paused else 'PAUSED_STALE_INPUT' if not fresh
                                   else 'PAUSED_METADATA_UNAVAILABLE' if not current
                                   else 'PAUSED_NO_FRESH_PREDICTION' if not predictions else 'MONITORING')
        reports[name]=report
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('export','watch'))
    parser.add_argument('--source',type=Path)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--state',type=Path)
    parser.add_argument('--group',type=int)
    parser.add_argument('--all-markets',action='store_true',help='Additional independent market-local research wallets; preserves BTC controls')
    parser.add_argument('--execution-evidence',action='store_true')
    args=parser.parse_args()
    if args.command=='export':
        export(args.source,args.input,args.group,all_markets=args.all_markets,execution_evidence=args.execution_evidence)
        return
    bots={name:Sandbox(args.state/('champion-directional-v1.sqlite' if name=='Champion' else 'challenger-b-directional-v1.sqlite'),
                       SandboxConfig(model_version=model)) for name,model in MODELS.items()}
    market_bots={}
    if args.all_markets:
        market_bots={asset+'_'+str(duration//60)+'m':Sandbox(args.state/(asset.lower()+'-'+str(duration)+'-research-directional-v1.sqlite'),
                     MarketSandboxConfig(model_version=RESEARCH_MODEL,asset=asset,duration_seconds=duration))
                     for asset,duration in MARKET_STREAMS}
    status=sqlite3.connect(args.state/'comparison.sqlite',timeout=15)
    status.execute('CREATE TABLE IF NOT EXISTS bot_snapshot (id INTEGER PRIMARY KEY, observed_at REAL,payload TEXT)')
    status.execute('CREATE TABLE IF NOT EXISTS signal_observations (exported_at REAL,model TEXT,market_slug TEXT,observed_at REAL,payload TEXT,PRIMARY KEY(exported_at,model,market_slug))')
    try:
        while True:
            now=time.time()
            try:
                data=json.loads(args.input.read_text())
            except (OSError,ValueError):
                data=dict(exported_at=0,markets=[],predictions=[])
            paused=(args.state/'STOP-SANDBOX').exists()
            report=run_cycle(bots,data,now,paused=paused)
            if market_bots: report['market_portfolios']=run_market_cycles(market_bots,data,now,paused=paused)
            with status:
                if report['input_status']=='FRESH':
                    for prediction in data['predictions']:
                        status.execute('INSERT OR IGNORE INTO signal_observations VALUES (?,?,?,?,?)',
                            (data['exported_at'],prediction['model_version'],prediction['market_slug'],now,json.dumps(prediction)))
                status.execute('INSERT INTO bot_snapshot VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',
                               (now,json.dumps(report,allow_nan=False)))
            print(json.dumps(dict(mode=report['operation_mode'],input_status=report['input_status'],
                                  common_signal_markets=report['common_signal_markets'])),flush=True)
            time.sleep(5)
    finally:
        status.close()
        for bot in list(bots.values())+list(market_bots.values()): bot.close()


if __name__=='__main__': main()
