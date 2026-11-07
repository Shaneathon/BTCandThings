"""Entry-only paper experiment. Observed volatility is NOT a return forecast."""
from dataclasses import dataclass
from decimal import Decimal
import json
from coinbase_bot.observed import ObservedBot,ObservedConfig
from coinbase_bot.market_data import positive


@dataclass(frozen=True)
class FeeFilterConfig(ObservedConfig):
    strategy_version: str='COINBASE_FEE_FILTER_V1'
    minimum_return15: str='.003'
    minimum_ema_gap: str='.001'
    minimum_cost_buffer: str='.003'

    def validate(self):
        super().validate()
        if (self.strategy_version!='COINBASE_FEE_FILTER_V1' or self.minimum_return15!='.003'
                or self.minimum_ema_gap!='.001' or self.minimum_cost_buffer!='.003'):
            raise ValueError('Use a separate strategy version for changed filters')
        return self


class FeeFilterBot(ObservedBot):
    def __init__(self,path,config=None):
        super().__init__(path,config or FeeFilterConfig())
        self.db.execute('CREATE TABLE IF NOT EXISTS experiment_metadata(key TEXT PRIMARY KEY,value REAL)')
        self.db.commit()

    def signal(self,source):
        signal=super().signal(source)
        if signal['direction']!='BUY': return signal
        product=source['product_id']
        if self.db.execute('SELECT 1 FROM positions WHERE product_id=?',(product,)).fetchone(): return signal
        bars=source['candles'][-60:]
        closes=[positive(b['close']) for b in bars]
        price=closes[-1]
        range60=(max(positive(b['high']) for b in bars)-min(positive(b['low']) for b in bars))/price
        return15=price/closes[-16]-1
        gap=positive(signal['ema9'])/positive(signal['ema21'])-1
        fee=positive(self.config.fee_rate)
        fee_break_even=(1+fee)/(1-fee)-1
        spread=(positive(source['ask'])-positive(source['bid']))/positive(source['ask'])
        threshold=fee_break_even+2*spread+2*positive(self.config.slippage_rate)+positive(self.config.minimum_cost_buffer)
        passed=(range60>=threshold and return15>=positive(self.config.minimum_return15)
                and gap>=positive(self.config.minimum_ema_gap))
        signal.update(entry_filter='PASS' if passed else 'FEE_AND_TREND_FILTER',
                      observed_range60=str(range60),observed_return15=str(return15),ema_gap_fraction=str(gap),
                      minimum_range_after_costs=str(threshold),range_is_return_forecast=False)
        if not passed: signal['direction']='HOLD'
        return signal

    def cycle(self,snapshots,now,kill_switch=False):
        old=self.db.execute('SELECT observed_at FROM bot_snapshot WHERE id=1').fetchone()
        if old and now<old[0]: raise ValueError('Clock moved backwards')
        with self.db: self.db.execute("INSERT OR IGNORE INTO experiment_metadata VALUES('started_at',?)",(now,))
        report=super().cycle(snapshots,now,kill_switch)
        for d in report['decisions']:
            if d.get('reason')=='NO_BUY_TREND' and d.get('signal',{}).get('entry_filter')=='FEE_AND_TREND_FILTER':
                d['reason']='FEE_AND_TREND_FILTER'
                with self.db: self.db.execute('UPDATE decision_journal SET payload=? WHERE product_id=? AND observed_at=?',(json.dumps(d),d['product_id'],now))
        report['experiment_started_at']=self.db.execute("SELECT value FROM experiment_metadata WHERE key='started_at'").fetchone()[0]
        report['strategy_version']=self.config.strategy_version
        report['experiment_note']='Entry-filter hypothesis only: recent range is not a forecast or demonstrated edge. Execution, fees, exits and risk remain equal to baseline.'
        with self.db: self.db.execute('UPDATE bot_snapshot SET payload=? WHERE id=1',(json.dumps(report),))
        return report
