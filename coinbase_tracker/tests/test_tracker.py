from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from coinbase_bot.tests.test_coinbase import public_fixture,NOW
from coinbase_tracker.collector import Store,collect,snapshot
from coinbase_tracker.client import bot_inputs


def fixture(url,params=None):
    if url.endswith('/ticker'):
        product=url.split('/')[-2]
        return {'trades':[dict(trade_id=str(i),product_id=product,time=datetime.fromtimestamp(NOW-i,timezone.utc).isoformat(),
                              price='105.9',size='1',side='BUY' if i%2 else 'SELL') for i in (1,2)]}
    return public_fixture(url,params)


class TrackerTests(unittest.TestCase):
    def test_public_request_starts_are_paced(self):
        from unittest.mock import patch
        from coinbase_tracker.collector import paced_get_json
        with patch('coinbase_tracker.collector._last_request',100),patch('coinbase_tracker.collector.time.monotonic',side_effect=[100.1,100.25]),patch('coinbase_tracker.collector.time.sleep') as wait,patch('coinbase_tracker.collector.get_json',return_value={}) as request:
            paced_get_json('https://api.coinbase.com/example')
        self.assertAlmostEqual(wait.call_args.args[0],.15)
        request.assert_called_once()

    def test_seed_is_private_consistent_and_exclusive(self):
        from coinbase_tracker.storage import seed
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.sqlite'
            target=Path(tmp)/'target.sqlite'
            store=Store(source)
            collect(store,fixture,NOW)
            store.close()
            seed(source,target)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(snapshot(source),snapshot(target))
            before=target.read_bytes()
            with self.assertRaises(FileExistsError): seed(source,target)
            self.assertEqual(before,target.read_bytes())

    def test_all_four_products_and_component_archival(self):
        store=Store(':memory:')
        result=collect(store,fixture,NOW)
        self.assertTrue(result['all_components_ready'],result)
        self.assertTrue(result['all_products_ready'])
        self.assertEqual(len(result['products']),4)
        self.assertEqual(store.db.execute('SELECT count(*) FROM candles').fetchone()[0],240)
        self.assertEqual(store.db.execute('SELECT count(*) FROM trades').fetchone()[0],8)
        self.assertEqual(store.db.execute('SELECT count(*) FROM observations').fetchone()[0],16)
        collect(store,fixture,NOW)
        self.assertEqual(store.db.execute('SELECT count(*) FROM trades').fetchone()[0],8)
        self.assertEqual(store.db.execute('SELECT count(*) FROM observations').fetchone()[0],16)
        for state in result['products'].values():
            self.assertTrue(state['indicators']['ready'])
            self.assertEqual(state['indicators']['direction'],'BUY')
            self.assertEqual(state['quality']['candle_gap_count'],0)
            self.assertEqual(state['book']['depth_imbalance'],0)
        store.close()

    def test_trade_feed_outage_preserves_other_components(self):
        def get(url,params=None):
            if url.endswith('/ticker'): raise TimeoutError()
            return fixture(url,params)
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertFalse(result['all_components_ready'])
        self.assertTrue(result['all_products_ready'])
        for state in result['products'].values():
            self.assertEqual(state['components']['trades'],'UNAVAILABLE')
            self.assertTrue(state['indicators']['ready'])
        self.assertEqual(store.db.execute('SELECT count(*) FROM candles').fetchone()[0],240)
        store.close()

    def test_wrong_books_and_gapped_candles_pause_bot_not_other_assets(self):
        def get(url,params=None):
            payload=fixture(url,params)
            if '/ETH-USD/candles' in url: payload['candles'].pop(10)
            if url.endswith('/product_book') and params['product_id']=='BTC-USD': payload['pricebook']['product_id']='SOL-USD'
            return payload
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertFalse(result['products']['BTC-USD']['bot_ready'])
        self.assertFalse(result['products']['ETH-USD']['bot_ready'])
        self.assertTrue(result['products']['SOL-USD']['bot_ready'])
        self.assertIn('book',result['products']['BTC-USD']['errors'])
        store.close()

    def test_conflicting_trade_id_does_not_overwrite_archive(self):
        store=Store(':memory:')
        collect(store,fixture,NOW)
        before=store.db.execute('SELECT payload FROM trades ORDER BY product,trade_id').fetchall()
        def get(url,params=None):
            response=fixture(url,params)
            if 'trades' in response: response['trades'][0]['price']='999'
            return response
        result=collect(store,get,NOW+1)
        self.assertEqual(before,store.db.execute('SELECT payload FROM trades ORDER BY product,trade_id').fetchall())
        self.assertTrue(all('trades' in p['errors'] for p in result['products'].values()))
        store.close()

    def test_archive_restart_and_read_only_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coin.sqlite'
            store=Store(path)
            collect(store,fixture,NOW)
            store.close()
            before=path.read_bytes()
            result=snapshot(path)
            self.assertEqual(result['venue'],'Coinbase Advanced')
            self.assertEqual(before,path.read_bytes())
            store=Store(path)
            collect(store,fixture,NOW)
            self.assertEqual(store.db.execute('SELECT count(*) FROM candles').fetchone()[0],240)
            store.close()

    def test_foreign_wallet_not_modified(self):
        from coinbase_bot.core import PaperBot
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cbot.sqlite'
            bot=PaperBot(path);bot.close()
            before=path.read_bytes()
            with self.assertRaises(ValueError): Store(path)
            self.assertEqual(before,path.read_bytes())

    def test_feature_observations_are_not_backdated_or_duplicated(self):
        store=Store(':memory:')
        collect(store,fixture,NOW)
        first=store.db.execute('SELECT product,candle_end,observed_at FROM features ORDER BY product').fetchall()
        self.assertEqual(len(first),4)
        self.assertTrue(all(row[2]==NOW for row in first))
        collect(store,fixture,NOW+1)
        self.assertEqual(first,store.db.execute('SELECT product,candle_end,observed_at FROM features ORDER BY product').fetchall())
        store.close()

    def test_client_rejects_bot_status_or_unsafe_token_destination(self):
        from io import BytesIO
        from unittest.mock import patch,Mock
        from coinbase_tracker.client import fetch
        opener=Mock()
        opener.open.side_effect=lambda *args,**kwargs:BytesIO(json.dumps({'mode':'PAPER','venue':'Coinbase Advanced','orders_enabled':False}).encode())
        with patch('coinbase_tracker.client.build_opener',return_value=opener),self.assertRaises(ValueError):
            fetch('https://example.com/status','x'*32)
        with self.assertRaises(ValueError): fetch('http://example.com/status','x'*32)

    def test_read_only_feed_can_supply_cbot_without_wallet_sharing(self):
        from coinbase_bot.core import PaperBot
        store=Store(':memory:')
        report=collect(store,fixture,NOW)
        bot=PaperBot(':memory:')
        result=bot.cycle(bot_inputs(report,NOW),NOW)
        self.assertTrue(result['account']['positions'])
        self.assertFalse(result['account']['live_orders_enabled'])
        with self.assertRaises(ValueError): bot_inputs(report,NOW+121)
        with self.assertRaises(ValueError): bot_inputs({'mode':'PAPER','venue':'Coinbase Advanced','observed_at':NOW},NOW)
        bot.close();store.close()


if __name__=='__main__': unittest.main()
