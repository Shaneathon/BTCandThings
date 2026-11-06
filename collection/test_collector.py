import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from collector import ASSETS, Store, candles, collect, get_json, iso, market

NOW = 1800000060
START = NOW // 900 * 900


def fixture_get(url, params=None):
    if params:
        return {'error': [], 'result': {params['pair']: [
            [NOW-120, '10', '12', '9', '11', '10', '5', 2],
            [NOW-60, '11', '13', '10', '12', '11', '6', 2],
            [NOW, '12', '14', '11', '13', '12', '1', 1]], 'last': NOW}}
    slug = url.rsplit('/', 1)[1]
    if '/events/' in url:
        return {'event': {'slug': slug, 'markets': [{'slug': slug + '-contract'}]}}
    from datetime import datetime
    event = slug.removesuffix('-contract')
    asset = event.split('-')[0].upper()
    start = datetime.strptime(event.split('-15m-')[1], '%Y-%m-%d-%H%Mz').replace(tzinfo=__import__('datetime').timezone.utc).timestamp()
    return {'market': {'slug': slug, 'assetPriceTerms': {
        'asset': {'symbol': asset}, 'marketType': 'UP_DOWN',
        'windowStart': iso(start), 'windowEnd': iso(start+900),
        'priceToBeat': {'currency': 'USD', 'value': '100'}}}}


class CollectionTests(unittest.TestCase):
    def test_429_is_not_retried_in_a_tight_loop(self):
        with patch('collector.urlopen',side_effect=HTTPError('url',429,'limited',{},None)) as request,patch('collector.time.sleep') as sleep:
            with self.assertRaises(HTTPError): get_json('https://example.com')
            self.assertEqual(request.call_count,1)
            sleep.assert_not_called()

    def test_bounded_network_retries(self):
        with patch('collector.urlopen', side_effect=URLError('offline')) as request, patch('collector.time.sleep'):
            with self.assertRaises(URLError):
                get_json('https://example.com')
            self.assertEqual(request.call_count, 3)
        with patch('collector.urlopen', side_effect=HTTPError('url', 404, 'missing', {}, None)) as request:
            with self.assertRaises(HTTPError):
                get_json('https://example.com')
            self.assertEqual(request.call_count, 1)

    def test_all_assets_completed_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.sqlite'
            store = Store(path)
            result = collect(store, fixture_get, NOW)
            for asset in ASSETS:
                self.assertEqual(result[asset]['candles_changed'], 2)
                self.assertEqual(result[asset]['markets_changed'], 3)
                self.assertFalse(result[asset]['stale'])
                self.assertEqual(result[asset]['market_errors'], [])
            self.assertEqual(store.db.execute('SELECT count(*) FROM records').fetchone()[0], 20)
            payloads = store.db.execute("SELECT payload FROM records WHERE kind='market'").fetchall()
            self.assertTrue(all('"settlement_status": "PENDING"' in r[0] for r in payloads))
            store.db.close()
            store = Store(path)
            result = collect(store, fixture_get, NOW)
            self.assertTrue(all(v['candles_changed'] == v['markets_changed'] == 0 for v in result.values()))
            store.db.close()

    def test_identity_and_target_rejection(self):
        for field, value in [('asset', {'symbol': 'SOL'}), ('windowEnd', iso(START+300)),
                             ('priceToBeat', {'currency': 'EUR', 'value': 10}),
                             ('priceToBeat', {'currency': 'USD', 'value': 'NaN'}),
                             ('windowStart', iso(START).replace('+00:00', ''))]:
            def get(url):
                response = copy.deepcopy(fixture_get(url))
                if 'market' in response:
                    response['market']['assetPriceTerms'][field] = value
                return response
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                market(get, 'BTC', START, NOW)

    def test_ambiguous_event_rejected(self):
        with self.assertRaises(ValueError):
            market(lambda url: {'slug': url.rsplit('/', 1)[1], 'markets': []}, 'BTC', START, NOW)

    def test_invalid_prices_and_duplicates(self):
        raw = fixture_get('', {'pair': 'XBTUSD'})
        series = raw['result']['XBTUSD']
        for bad in ('NaN', '-1', 'inf'):
            payload = copy.deepcopy(raw)
            payload['result']['XBTUSD'][0][4] = bad
            with self.assertRaises(ValueError):
                candles(payload, 'BTC', NOW)
        series.append(copy.deepcopy(series[0]))
        self.assertEqual(len(candles(raw, 'BTC', NOW)), 2)
        series[-1][4] = '10'
        with self.assertRaises(ValueError):
            candles(raw, 'BTC', NOW)

    def test_failure_isolation_and_staleness(self):
        def get(url, params=None):
            if params and params['pair'] == 'ETHUSD':
                raise TimeoutError()
            return fixture_get(url, params)
        store = Store(':memory:')
        result = collect(store, get, NOW)
        self.assertEqual(result['ETH']['candle_error'], 'TimeoutError')
        self.assertEqual(result['SOL']['candles_changed'], 2)
        def stale(url, params=None):
            if params:
                return {'result': {'pair': [[NOW-600,10,12,9,11,10,1,1]], 'last': NOW}, 'error': []}
            return fixture_get(url)
        result = collect(store, stale, NOW)
        self.assertTrue(all(v['stale'] for v in result.values()))
        store.db.close()


if __name__ == '__main__':
    unittest.main()
