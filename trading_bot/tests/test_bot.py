from dataclasses import replace
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from trading_bot.core import Config, PaperBot, STREAMS
from trading_bot.live import LiveGateway, LiveTradingDisabled, build_limit_order

NOW=1800000060
MODEL=Config().model_version


def iso(t):
    return datetime.fromtimestamp(t,timezone.utc).isoformat()


def fixtures(streams=None):
    markets,predictions,quotes=[],[],[]
    for asset,seconds in sorted(streams or STREAMS):
        start=NOW//seconds*seconds
        current=f'{asset.lower()}-{seconds}-{start}'
        market=dict(market_slug=current,asset=asset,duration_seconds=seconds,window_start=iso(start),
            window_end=iso(start+seconds),contract_slug=current+'-contract',official_price_to_beat=100,settlement_status='PENDING')
        markets.append(market)
        predictions.append(dict(market_slug=current,model_version=MODEL,recorded_at=iso(NOW-2),source_timestamp=iso(NOW-3),
                                predicted_up_probability=.8,lean_direction='UP'))
        quotes.append(dict(market_slug=current,contract_slug=market['contract_slug'],captured_at=iso(NOW-1),
            source_name='Polymarket US',side_mapping_verified=True,side_mapping_evidence='Reviewed test mapping',
            up_ask=.5,up_bid=.49,down_ask=.52,down_bid=.5,up_ask_size=100,down_ask_size=100))
        for i in range(2):
            old_start=start-seconds*(i+2)
            slug=current+'-history-'+str(i)
            markets.append(dict(market_slug=slug,asset=asset,duration_seconds=seconds,window_start=iso(old_start),
                window_end=iso(old_start+seconds),contract_slug=slug+'-contract',official_price_to_beat=100,
                settlement_status='VERIFIED',official_winner='UP',settled_at=iso(old_start+seconds+1),settlement_evidence='Synthetic official test evidence'))
            predictions.append(dict(market_slug=slug,model_version=MODEL,recorded_at=iso(old_start+(NOW-2-start)),
                source_timestamp=iso(old_start+(NOW-3-start)),predicted_up_probability=.8,lean_direction='UP'))
    return markets,predictions,quotes


class BotTests(unittest.TestCase):
    def setUp(self):
        self.config=replace(Config(),minimum_settled_markets=2)
        self.bot=PaperBot(':memory:',self.config)
    def tearDown(self):
        self.bot.close()

    def test_all_ten_streams_fill_within_wallet_and_exposure(self):
        data=fixtures()
        result=self.bot.cycle(*data,NOW)
        bought=[d for d in result['decisions'] if d['action']=='PAPER_BUY']
        self.assertEqual(len(bought),8,result['decisions'])
        self.assertEqual(len(result['account']['positions']),8)
        self.assertAlmostEqual(float(result['account']['cash']),920.96)
        self.assertAlmostEqual(float(result['account']['open_exposure']),79.04)
        self.assertFalse(result['account']['live_orders_enabled'])
        again=self.bot.cycle(*data,NOW+1)
        self.assertFalse(any(d['action']=='PAPER_BUY' for d in again['decisions']))
        self.assertEqual(result['account']['cash'],again['account']['cash'])

    def test_verified_settlement_pays_once_during_kill_switch(self):
        markets,predictions,quotes=fixtures({('BTC',300)})
        self.bot.cycle(markets,predictions,quotes,NOW)
        current=next(m for m in markets if m['settlement_status']=='PENDING')
        current.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+901),settlement_evidence='Synthetic final test evidence')
        result=self.bot.cycle(markets,predictions,quotes,NOW+901,kill_switch=True)
        self.assertEqual(result['account']['positions'][0]['state'],'PAPER_CLOSED')
        self.assertAlmostEqual(float(result['account']['realized_pnl']),9.12)
        again=self.bot.cycle(markets,predictions,quotes,NOW+902,kill_switch=True)
        self.assertEqual(result['account']['cash'],again['account']['cash'])

    def test_future_and_wrong_contract_final_do_not_pay(self):
        markets,predictions,quotes=fixtures({('BTC',300)})
        self.bot.cycle(markets,predictions,quotes,NOW)
        current=next(m for m in markets if m['settlement_status']=='PENDING')
        current.update(settlement_status='VERIFIED',official_winner='UP',settled_at=iso(NOW+901),settlement_evidence='Synthetic final test evidence')
        result=self.bot.cycle(markets,predictions,quotes,NOW+1)
        self.assertEqual(result['account']['positions'][0]['state'],'PAPER_OPEN')
        current['contract_slug']='wrong'
        result=self.bot.cycle(markets,predictions,quotes,NOW+902)
        self.assertEqual(result['account']['positions'][0]['state'],'PAPER_OPEN')

    def test_missing_history_unmapped_stale_quotes_and_no_edge(self):
        for mode in ('history','mapping','stale','edge','depth','spread','future'):
            bot=PaperBot(':memory:',self.config)
            markets,predictions,quotes=fixtures({('ETH',900)})
            if mode=='history': markets=[m for m in markets if m['settlement_status']=='PENDING']
            if mode=='mapping': quotes[0]['side_mapping_verified']=False
            if mode=='stale': quotes[0]['captured_at']=iso(NOW-50)
            if mode=='edge': quotes[0].update(up_ask=.8,up_bid=.79)
            if mode=='depth': quotes[0]['up_ask_size']=0
            if mode=='spread': quotes[0]['up_bid']=.1
            if mode=='future': predictions[0]['source_timestamp']=iso(NOW+1)
            result=bot.cycle(markets,predictions,quotes,NOW)
            self.assertFalse(result['account']['positions'],(mode,result))
            bot.close()

    def test_no_hindsight_history_or_cross_asset_calibration(self):
        markets,predictions,quotes=fixtures({('BTC',300)})
        for m in markets:
            if m['settlement_status']=='VERIFIED': m['settled_at']=iso(NOW+10)
        result=self.bot.cycle(markets,predictions,quotes,NOW)
        self.assertFalse(result['account']['positions'])
        self.assertIn('INSUFFICIENT_HISTORY',[d.get('reason') for d in result['decisions']])

    def test_kill_switch_and_capital_limits(self):
        result=self.bot.cycle(*fixtures(),NOW,kill_switch=True)
        self.assertFalse(result['account']['positions'])
        limited=PaperBot(':memory:',replace(self.config,max_open_positions=1))
        result=limited.cycle(*fixtures(),NOW)
        self.assertEqual(len(result['account']['positions']),1)
        limited.close()

    def test_drawdown_halt_persists(self):
        bot=PaperBot(':memory:',replace(self.config,max_drawdown='0.00988'))
        markets,predictions,quotes=fixtures({('SOL',300)})
        bot.cycle(markets,predictions,quotes,NOW)
        m=next(m for m in markets if m['settlement_status']=='PENDING')
        m.update(settlement_status='VERIFIED',official_winner='DOWN',settled_at=iso(NOW+901),settlement_evidence='test evidence')
        result=bot.cycle(markets,predictions,quotes,NOW+901)
        self.assertEqual(result['account']['halted_reason'],'MAX_REALIZED_DRAWDOWN')
        bot.close()

    def test_restart_and_configuration_immutability(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'paper.sqlite'
            bot=PaperBot(path,self.config)
            result=bot.cycle(*fixtures(),NOW)
            bot.close()
            bot=PaperBot(path,self.config)
            again=bot.cycle(*fixtures(),NOW+1)
            self.assertEqual(result['account']['cash'],again['account']['cash'])
            bot.close()
            with self.assertRaises(ValueError): PaperBot(path,replace(self.config,minimum_edge='.1'))

    def test_history_gate_is_independent_and_bad_brier_pauses_entries(self):
        for mode in ('asset','duration','score'):
            bot=PaperBot(':memory:',self.config)
            markets,predictions,quotes=fixtures({('BTC',300)})
            for market in markets:
                if market['settlement_status']=='VERIFIED':
                    if mode=='asset': market['asset']='ETH'
                    if mode=='duration': market['duration_seconds']=900
            if mode=='score':
                for prediction in predictions[1:]: prediction['predicted_up_probability']=.1
            result=bot.cycle(markets,predictions,quotes,NOW)
            self.assertFalse(result['account']['positions'])
            reason='HISTORICAL_SCORE_GATE' if mode=='score' else 'INSUFFICIENT_HISTORY'
            self.assertIn(reason,[d.get('reason') for d in result['decisions']])
            bot.close()

    def test_daily_risk_budget_reserves_open_worst_case_loss(self):
        bot=PaperBot(':memory:',replace(self.config,max_daily_loss='10'))
        result=bot.cycle(*fixtures(),NOW)
        self.assertEqual(len(result['account']['positions']),1)
        self.assertLessEqual(float(result['account']['open_exposure']),10)
        bot.close()

    def test_clock_rollback_does_not_mutate_ledger(self):
        result=self.bot.cycle(*fixtures(),NOW)
        with self.assertRaises(ValueError): self.bot.cycle(*fixtures(),NOW-1)
        self.assertEqual(result['account']['cash'],self.bot.status()['cash'])

    def test_live_payload_preview_and_submission_interlock(self):
        position=dict(contract_slug='contract',side='UP',entry_price='.51',quantity='10')
        mapping=dict(contract_slug='contract',verified=True,evidence='reviewed',up_buy_intent='ORDER_INTENT_BUY_LONG',down_buy_intent='ORDER_INTENT_BUY_SHORT')
        order=build_limit_order(position,mapping)
        self.assertEqual(order['tif'],'TIME_IN_FORCE_FILL_OR_KILL')
        self.assertEqual(order['quantity'],10)
        with self.assertRaises(ValueError): build_limit_order(position,{**mapping,'contract_slug':'wrong'})
        with self.assertRaises(LiveTradingDisabled): LiveGateway().submit(order)


if __name__=='__main__':
    unittest.main()
