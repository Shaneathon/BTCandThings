from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from coinbase_bot.observed import ObservedBot
from coinbase_bot.market_data import fetch_product
from coinbase_bot.tests.test_coinbase import NOW,public_fixture


class ObservedCoinbaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'observed.sqlite';self.bot=ObservedBot(self.path)
        self.data={'BTC-USD':fetch_product('BTC-USD',NOW,public_fixture)}

    def tearDown(self): self.bot.close();self.tmp.cleanup()

    def fresh(self,t,**values): self.data['BTC-USD'].update(observed_at=t,book_time=t,**values)

    def test_delayed_frozen_limit_buy_sell_and_restart(self):
        report=self.bot.cycle(self.data,NOW)
        self.assertFalse(report['account']['positions'])
        self.assertEqual(report['order_states'],{'PROPOSED':1})
        self.bot.close();self.bot=ObservedBot(self.path)
        self.bot.cycle(self.data,NOW+1)
        self.fresh(NOW+3)
        bought=self.bot.cycle(self.data,NOW+3)
        self.assertEqual(len(bought['account']['positions']),1)
        self.assertEqual(bought['account']['positions'][0]['entry_price'],'106')
        quantity=Decimal(bought['account']['positions'][0]['quantity'])
        self.assertEqual(Decimal(bought['account']['positions'][0]['cost']),quantity*106*Decimal('1.006'))
        self.fresh(NOW+4,bid='100',ask='100.1')
        proposed=self.bot.cycle(self.data,NOW+4,kill_switch=True)
        self.assertEqual(len(proposed['account']['positions']),1)
        self.fresh(NOW+7)
        sold=self.bot.cycle(self.data,NOW+7,kill_switch=True)
        self.assertFalse(sold['account']['positions'])
        self.assertEqual(sold['order_states'],{'FILLED':2})
        self.assertEqual(sold['market_pnl'][0]['closed_trades'],1)
        cash=sold['account']['cash']
        self.assertEqual(self.bot.cycle(self.data,NOW+8,kill_switch=True)['account']['cash'],cash)
        self.assertFalse(sold['account']['live_orders_enabled'])
        self.assertIn('ACCOUNT_TIER_NOT_CONNECTED',sold['fee_basis'])

    def test_limit_move_or_insufficient_size_is_unfilled_and_free(self):
        for change in [dict(ask='107',bid='106.9'),dict(ask_size='.001')]:
            bot=ObservedBot(':memory:')
            source={'BTC-USD':fetch_product('BTC-USD',NOW,public_fixture)}
            bot.cycle(source,NOW)
            source['BTC-USD'].update(observed_at=NOW+3,book_time=NOW+3,**change)
            result=bot.cycle(source,NOW+3)
            self.assertFalse(result['account']['positions'])
            self.assertEqual(result['account']['cash'],'1000')
            bot.close()

    def test_expiry_pause_and_clock_rollback(self):
        self.bot.cycle(self.data,NOW)
        with self.assertRaisesRegex(ValueError,'Clock'):
            self.bot.cycle(self.data,NOW-1)
        result=self.bot.cycle(self.data,NOW+1,kill_switch=True)
        self.assertEqual(result['order_states'],{'CANCELLED':1})
        self.assertFalse(result['account']['positions'])
        self.assertEqual(result['account']['cash'],'1000')

if __name__=='__main__': unittest.main()
