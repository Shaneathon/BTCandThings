import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from ten_streams import STREAMS, collect, validate, cooldown_until
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
    def test_quote_budget_honors_retry_after_and_rotates_unattempted_streams(self):
        store=Store(':memory:')
        calls=[]
        def get(url,params=None):
            if url.endswith('/bbo'):
                calls.append(url)
                if len(calls)==3: raise HTTPError(url,429,'limited',{'Retry-After':'120'},None)
            return fixture(url,params)
        first=collect(store,get,NOW)
        self.assertEqual(len(calls),3)
        self.assertTrue(first['recording_ready'])
        self.assertEqual(first['streams']['ETH_15m']['quote_status'],'RATE_LIMIT_COOLDOWN')
        collect(store,get,NOW+30)
        self.assertEqual(len(calls),3)
        collect(store,get,NOW+121)
        self.assertIn('eth-updown-15m',calls[3])
        self.assertEqual(len(calls),13)
        store.db.close()

    def test_quote_requests_are_paced_in_real_clock_mode(self):
        from quotes import initialize_budget,capture_managed
        store=Store(':memory:')
        initialize_budget(store)
        store.db.execute('INSERT INTO quote_budget VALUES (1,?,0)',(NOW-.5,))
        store.db.commit()
        row={'asset':'BTC','duration_seconds':300,'window_end':iso(NOW+100)}
        with patch('quotes.time.time',side_effect=[NOW,NOW+1]),patch('quotes.time.sleep') as wait,patch('quotes.capture',return_value={}) as captured:
            capture_managed(store,lambda *args:None,row)
        wait.assert_called_once_with(1.0)
        captured.assert_called_once()
        store.db.close()

    def test_rate_limit_cooldown_persists_and_recording_readiness_stays_explicit(self):
        store=Store(':memory:')
        def limited(url,params=None):
            if 'yahoo' in url: raise HTTPError(url,429,'rate limited',{'Retry-After':'1800'},None)
            return fixture(url,params)
        first=collect(store,limited,NOW)
        self.assertTrue(first['recording_ready'])
        self.assertFalse(first['collection_ready'])
        self.assertEqual(first['coverage_mode'],'AVAILABLE_DATA_WITH_REPORTED_GAPS')
        calls=[]
        def get(url,params=None):
            calls.append(url)
            return fixture(url,params)
        second=collect(store,get,NOW+1)
        self.assertFalse(any('yahoo' in url for url in calls))
        self.assertEqual(second['assets']['GOLD']['feed_error'],'RATE_LIMIT_COOLDOWN')
        self.assertEqual(second['assets']['GOLD']['retry_after'],iso(NOW+1800))
        self.assertEqual(cooldown_until(HTTPError('url',429,'limited',{'Retry-After':'Wed, 01 Jan 2031 00:00:00 GMT'},None),NOW),1924992000)
        store.db.close()

    def test_clock_rollover_before_stream_processing_uses_current_market(self):
        boundary=NOW//300*300+300
        clock={'calls':0}
        def current_time():
            clock['calls']+=1
            return boundary-1 if clock['calls']==1 else boundary+2
        store=Store(':memory:')
        with patch('test_ten_streams.NOW',boundary),patch('ten_streams.time.time',side_effect=current_time),patch('quotes.time.sleep'):
            result=collect(store,fixture)
        self.assertTrue(result['streams']['BTC_5m']['collection_ready'],result)
        self.assertEqual(result['streams']['BTC_5m']['window_end'],iso(boundary+300))
        store.db.close()

    def test_boundary_during_market_io_reloads_target_without_relabeling(self):
        boundary=NOW//300*300+300
        clock={'time':boundary-1,'rolled':False}
        def get(url,params=None):
            response=fixture(url,params)
            if '/events/' in url and 'btc-updown-5m' in url and not clock['rolled']:
                clock.update(time=boundary+2,rolled=True)
            return response
        store=Store(':memory:')
        with patch('test_ten_streams.NOW',boundary),patch('ten_streams.time.time',side_effect=lambda:clock['time']),patch('quotes.time.sleep'):
            result=collect(store,get)
        self.assertEqual(result['streams']['BTC_5m']['window_end'],iso(boundary+300))
        self.assertTrue(result['streams']['BTC_5m']['collection_ready'],result)
        store.db.close()

    def test_metals_http_status_is_reported_and_quotes_still_archived(self):
        def get(url,params=None):
            if 'yahoo' in url: raise HTTPError(url,429,'rate limited',{},None)
            return fixture(url,params)
        store=Store(':memory:')
        result=collect(store,get,NOW)
        self.assertEqual(result['assets']['GOLD']['http_status'],429)
        self.assertEqual(result['assets']['SILVER']['http_status'],429)
        self.assertEqual(store.db.execute('SELECT count(*) FROM raw_quotes').fetchone()[0],10)
        store.db.close()

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
