import tempfile
from pathlib import Path
import unittest
from ten_streams import STREAMS, collect, validate
from collector import Store, iso

NOW = 1800000060


def fixture(url, params=None):
    if url.endswith('/bbo'):
        return {'marketData':{'marketSlug':url.split('/')[-2], 'bestBid':{'value':.4},'bestAsk':{'value':.5}}}
    if 'kraken' in url:
        return {'error':[], 'result':{params['pair']:[
            [NOW-60*(61-i),100+i,102+i,99+i,101+i,100+i,10,1] for i in range(62)], 'last': NOW}}
    if 'yahoo' in url:
        return {'chart':{'result':[{'timestamp':[NOW-60*(61-i) for i in range(62)],
            'indicators':{'quote':[{'open':[100+i for i in range(62)],'high':[102+i for i in range(62)],
            'low':[99+i for i in range(62)],'close':[101+i for i in range(62)],'volume':[10]*62}]}}]}}
    from datetime import datetime, timezone
    slug = url.rsplit('/',1)[1]
    if '/events/' in url:
        return {'event':{'slug':slug, 'markets':[{'slug':slug+'-contract'}]}}
    asset, _, duration, date = slug.removesuffix('-contract').split('-',3)
    start = datetime.strptime(date,'%Y-%m-%d-%H%Mz').replace(tzinfo=timezone.utc).timestamp()
    seconds = 300 if duration == '5m' else 900
    return {'market':{'slug':slug, 'assetPriceTerms':{'asset':{'symbol':asset},
            'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN','windowStart':iso(start),
            'windowEnd':iso(start+seconds),'priceToBeat':{'currency':'USD','value':150}}}}


class TenStreamTests(unittest.TestCase):
    def test_ten_streams_share_six_feeds_and_save_real_observation_times(self):
        calls=[]
        def get(url, params=None):
            calls.append(url)
            return fixture(url,params)
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertEqual(len(STREAMS),10)
        self.assertTrue(result['collection_ready'],result)
        self.assertFalse(result['simulation_ready'])
        self.assertEqual(sum('kraken' in u or 'yahoo' in u for u in calls),6)
        self.assertEqual(sum(s['predictions_saved'] for s in result['streams'].values()),10)
        self.assertEqual(store.db.execute('SELECT DISTINCT recorded_at FROM research_snapshots').fetchall(),[(iso(NOW),)])
        result=collect(store,get,NOW)
        self.assertEqual(sum(s['predictions_saved'] for s in result['streams'].values()),0)
        store.db.close()

    def test_metals_outage_is_visible_crypto_keeps_collecting(self):
        def get(url, params=None):
            if 'yahoo' in url:
                raise TimeoutError()
            return fixture(url,params)
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertFalse(result['collection_ready'])
        self.assertEqual(sum(s['collection_ready'] for s in result['streams'].values()),8)
        self.assertIn('feed_error',result['assets']['GOLD'])
        store.db.close()

    def test_restart_validation_and_stale_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.sqlite'
            store=Store(path)
            collect(store,fixture,NOW)
            store.db.close()
            result=validate(path,NOW+60)
            self.assertTrue(result['collection_ready'])
            self.assertEqual(result['total_prediction_snapshots'],10)
            self.assertFalse(validate(path,NOW+181)['collection_ready'])

    def test_wrong_crypto_contract_cannot_save_prediction(self):
        def get(url, params=None):
            result=fixture(url,params)
            if '/market/' in url and '/eth-' in url:
                result['market']['assetPriceTerms']['asset']['symbol']='btc'
            return result
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertFalse(result['streams']['ETH_5m']['collection_ready'])
        self.assertFalse(result['streams']['ETH_15m']['collection_ready'])
        self.assertEqual(store.db.execute("SELECT count(*) FROM research_snapshots WHERE market_slug LIKE 'eth-%'").fetchone()[0],0)
        store.db.close()


if __name__=='__main__':
    unittest.main()
