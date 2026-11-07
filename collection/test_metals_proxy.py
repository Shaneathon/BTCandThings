import os
from unittest.mock import patch
import unittest
from ten_streams import load_candles


class MetalsProxyTests(unittest.TestCase):
    def test_new_source_is_exact_asset_and_never_silently_falls_back_to_futures(self):
        calls=[]
        def get(url,params):
            calls.append(url)
            return dict(asset='SILVER',currency='USD',source_symbol='XAG/USD',
                        is_official_settlement_feed=False,candles=[])
        with patch.dict(os.environ,BTC_METALS_PROXY_URL='http://127.0.0.1:8770'):
            frame,label=load_candles(get,'SILVER',None,1794009600)
            self.assertTrue(frame.empty)
            self.assertIn('NOT official Chainlink',label)
            with self.assertRaises(ValueError): load_candles(get,'GOLD',None,1794009600)
        self.assertTrue(all(url.startswith('http://127.0.0.1:8770/') for url in calls))

    def test_collector_preserves_proxy_provenance_and_no_official_claim(self):
        import json
        from collector import Store
        from ten_streams import collect
        from test_ten_streams import fixture,NOW
        def get(url,params=None):
            if url.startswith('http://127.0.0.1:8770/'):
                asset=params['asset']
                return dict(asset=asset,currency='USD',source_symbol='XAU/USD' if asset=='GOLD' else 'XAG/USD',
                            is_official_settlement_feed=False,candles=[
                    dict(time=NOW-60*(61-i),open=100+i,high=102+i,low=99+i,close=101+i,volume=None) for i in range(61)])
            return fixture(url,params)
        store=Store(':memory:')
        try:
            with patch.dict(os.environ,BTC_METALS_PROXY_URL='http://127.0.0.1:8770'):
                result=collect(store,get,NOW)
            self.assertTrue(result['streams']['GOLD_15m']['collection_ready'])
            rows=[json.loads(row[0]) for row in store.db.execute("SELECT payload FROM records WHERE kind='candle'")]
            metals=[row for row in rows if row['asset'] in ('GOLD','SILVER')]
            self.assertTrue(metals)
            self.assertTrue(all(row['source_name']=='Gold-API sampled spot proxy' and row['is_official_settlement_feed'] is False for row in metals))
            self.assertEqual({r['source_symbol'] for r in metals},{'XAU/USD','XAG/USD'})
        finally: store.db.close()
