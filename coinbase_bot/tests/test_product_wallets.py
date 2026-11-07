from decimal import Decimal
from pathlib import Path
import json
import tempfile
import unittest
from coinbase_bot.observed import ObservedBot
from coinbase_bot.product_wallets import migrate,open_bot,aggregate
from coinbase_bot.tests.test_coinbase import NOW,public_fixture
from coinbase_bot.market_data import fetch_product,PRODUCTS

class ProductWalletTests(unittest.TestCase):
    def test_migration_preserves_source_cash_history_holdings_and_exit_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'shared.sqlite';dest=root/'products'
            old=ObservedBot(source)
            btc=fetch_product('BTC-USD',NOW,public_fixture)
            old.cycle({'BTC-USD':btc},NOW)
            btc.update(book_time=NOW+3,observed_at=NOW+3)
            bought=old.cycle({'BTC-USD':btc},NOW+3)
            btc.update(book_time=NOW+4,observed_at=NOW+4,bid='100',ask='100.1')
            old.cycle({'BTC-USD':btc},NOW+4)
            cash=Decimal(bought['account']['cash']);old.close();original=source.read_bytes()
            summary=migrate(source,dest,'baseline',NOW+5)
            self.assertEqual(sum(Decimal(r['cash']) for r in summary),cash)
            self.assertEqual(source.read_bytes(),original)
            bots={product:open_bot(dest/(product+'.sqlite'),'baseline') for product in PRODUCTS}
            btc.update(book_time=NOW+7,observed_at=NOW+7)
            reports={product:bot.cycle({'BTC-USD':btc},NOW+7) for product,bot in bots.items()}
            self.assertEqual(reports['BTC-USD']['market_pnl'][0]['closed_trades'],1)
            self.assertEqual(reports['ETH-USD']['account']['cash'],'250')
            self.assertEqual(reports['SOL-USD']['account']['realized_pnl'],'0')
            self.assertEqual(reports['BTC-USD']['configuration']['max_daily_loss'],'25')
            self.assertFalse(reports['BTC-USD']['account']['positions'])
            with self.assertRaisesRegex(ValueError,'WRONG_ISOLATED'):
                bots['BTC-USD'].execute({'product_id':'ETH-USD'},'BUY',Decimal(1),NOW+8)
            combined=aggregate(reports,'baseline',NOW+7)
            self.assertEqual(combined['operation_mode'],'PRODUCT_WALLETS_PAPER')
            self.assertFalse(combined['account']['live_orders_enabled'])
            for bot in bots.values(): bot.close()
            with self.assertRaisesRegex(ValueError,'Destination exists'): migrate(source,dest,'baseline',NOW+9)

    def test_all_coin_feed_cannot_spend_another_coins_funds(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'shared.sqlite';dest=root/'products'
            old=ObservedBot(source);old.cycle({},NOW);old.close()
            migrate(source,dest,'baseline',NOW+1)
            btc=open_bot(dest/'BTC-USD.sqlite','baseline');eth=open_bot(dest/'ETH-USD.sqlite','baseline')
            feed={product:fetch_product(product,NOW,public_fixture) for product in PRODUCTS}
            for s in feed.values(): s.update(book_time=NOW+2,observed_at=NOW+2)
            btc.cycle(feed,NOW+2)
            for s in feed.values(): s.update(book_time=NOW+5,observed_at=NOW+5)
            report=btc.cycle(feed,NOW+5)
            self.assertEqual(len(report['account']['positions']),1)
            self.assertTrue(all(p['product_id']=='BTC-USD' for p in report['account']['positions']))
            self.assertLessEqual(Decimal(report['account']['open_exposure']),Decimal(25))
            self.assertEqual(eth.db.execute('SELECT cash FROM account WHERE id=1').fetchone()[0],'250')
            btc.close();eth.close()

    def test_closed_history_pnl_is_assigned_to_only_its_product(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'shared.sqlite';dest=root/'products'
            old=ObservedBot(source);btc=fetch_product('BTC-USD',NOW,public_fixture)
            old.cycle({'BTC-USD':btc},NOW)
            btc.update(book_time=NOW+3,observed_at=NOW+3);old.cycle({'BTC-USD':btc},NOW+3)
            btc.update(book_time=NOW+4,observed_at=NOW+4,bid='100',ask='100.1');old.cycle({'BTC-USD':btc},NOW+4)
            btc.update(book_time=NOW+7,observed_at=NOW+7);closed=old.cycle({'BTC-USD':btc},NOW+7)
            pnl=Decimal(closed['account']['realized_pnl']);old.close()
            rows=migrate(source,dest,'baseline',NOW+8)
            self.assertEqual(Decimal(rows[0]['realized_pnl']),pnl)
            self.assertEqual(rows[0]['closed_trades'],1)
            self.assertTrue(all(row['realized_pnl']=='0' for row in rows[1:]))
            self.assertEqual(sum(Decimal(r['cash']) for r in rows),Decimal(1000)+pnl)

    def test_fee_experiment_migrates_without_resetting_original_start(self):
        from coinbase_bot.fee_filter import FeeFilterBot
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'shared.sqlite';dest=root/'products'
            old=FeeFilterBot(source);old.cycle({},NOW);old.close()
            migrate(source,dest,'fee-filter',NOW+10)
            new=open_bot(dest/'ETH-USD.sqlite','fee-filter')
            result=new.cycle({},NOW+11)
            self.assertEqual(result['experiment_started_at'],NOW)
            self.assertEqual(result['selected_product'],'ETH-USD')
            self.assertEqual(result['configuration']['initial_cash'],'250')
            new.close()

    def test_unsubmitted_buys_cancel_without_fees_or_fund_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'shared.sqlite';dest=root/'products'
            bot=ObservedBot(source);bot.cycle({'BTC-USD':fetch_product('BTC-USD',NOW,public_fixture)},NOW);bot.close()
            summary=migrate(source,dest,'baseline',NOW+1)
            self.assertEqual(sum(Decimal(r['cash']) for r in summary),Decimal(1000))
            product=open_bot(dest/'BTC-USD.sqlite','baseline')
            state=product.cycle({},NOW+2)
            self.assertEqual(state['order_states'],{'CANCELLED':1})
            self.assertEqual(state['account']['cash'],'250')
            self.assertEqual(state['account']['realized_pnl'],'0')
            self.assertEqual(state['selected_product'],'BTC-USD')
            product.close()

if __name__=='__main__': unittest.main()
