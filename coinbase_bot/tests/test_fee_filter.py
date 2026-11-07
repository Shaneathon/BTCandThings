import copy
from pathlib import Path
import tempfile
import unittest
from coinbase_bot.observed import ObservedBot
from coinbase_bot.fee_filter import FeeFilterBot
from coinbase_bot.market_data import fetch_product
from coinbase_bot.tests.test_coinbase import NOW,public_fixture
from coinbase_bot.comparison import compare

class FilterTests(unittest.TestCase):
    def test_low_movement_buy_is_filtered_without_changing_baseline(self):
        baseline=ObservedBot(':memory:');variant=FeeFilterBot(':memory:')
        source=fetch_product('BTC-USD',NOW,public_fixture)
        for i,bar in enumerate(source['candles']):
            v=100+i*.001
            bar.update(open=str(v),high=str(v+.002),low=str(v-.002),close=str(v))
        source.update(bid='100.058',ask='100.06')
        data={'BTC-USD':source}
        ordinary=baseline.cycle(data,NOW);filtered=variant.cycle(data,NOW)
        self.assertEqual(ordinary['order_states'],{'PROPOSED':1})
        self.assertEqual(filtered['order_states'],{})
        decision=filtered['decisions'][0]
        self.assertEqual(decision['reason'],'FEE_AND_TREND_FILTER')
        self.assertFalse(decision['signal']['range_is_return_forecast'])
        self.assertEqual(filtered['account']['cash'],'1000')
        baseline.close();variant.close()

    def test_strong_trend_uses_same_delayed_execution_and_fee_basis(self):
        bot=FeeFilterBot(':memory:');source=fetch_product('BTC-USD',NOW,public_fixture)
        first=bot.cycle({'BTC-USD':source},NOW)
        self.assertEqual(first['order_states'],{'PROPOSED':1})
        source.update(book_time=NOW+3,observed_at=NOW+3)
        later=bot.cycle({'BTC-USD':source},NOW+3)
        self.assertEqual(later['order_states'],{'FILLED':1})
        self.assertEqual(later['account']['positions'][0]['entry_price'],'106')
        self.assertFalse(later['account']['live_orders_enabled'])
        bot.close()

    def test_comparison_uses_common_forward_start_and_separate_read_only_ledgers(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'baseline.sqlite',Path(folder)/'challenger.sqlite'
            baseline=ObservedBot(a);challenger=FeeFilterBot(b)
            baseline.cycle({},NOW-1);challenger.cycle({},NOW)
            baseline.close();challenger.close()
            before=(a.read_bytes(),b.read_bytes())
            report=compare(a,b,NOW+1)
            self.assertEqual(report['started_at'],NOW)
            self.assertTrue(report['challenger_status_fresh'])
            self.assertEqual(len(report['aligned_closed_trade_results']),2)
            self.assertEqual((a.read_bytes(),b.read_bytes()),before)

if __name__=='__main__': unittest.main()
