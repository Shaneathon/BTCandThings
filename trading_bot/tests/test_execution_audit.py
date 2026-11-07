from datetime import datetime, timezone
from email.message import Message
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.error import HTTPError
from trading_bot.execution_audit import audit, book_summary, inspect_market

NOW = 1794010950

def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def book():
    return {'marketData': {'marketSlug': 'exact-contract', 'state': 'MARKET_STATE_OPEN',
            'transactTime': iso(NOW-1),
            'bids': [{'px': {'value': '.60', 'currency': 'USD'}, 'qty': '7'}],
            'offers': [{'px': {'value': '.65', 'currency': 'USD'}, 'qty': '3'}]}}


def market():
    return dict(market_slug='btc-event', contract_slug='exact-contract', asset='BTC',
                duration_seconds=900, window_start=iso(NOW-100), window_end=iso(NOW+800),
                official_price_to_beat='75000')


def metadata():
    return {'market': {'slug': 'exact-contract', 'assetPriceTerms': {
        'asset': {'symbol': 'btc'}, 'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
        'windowStart': iso(NOW-100), 'windowEnd': iso(NOW+800),
        'priceToBeat': {'value': '75000', 'currency': 'USD'}},
        'marketSides': [{'description': 'Yes', 'long': True}, {'description': 'No', 'long': False}],
        'feeCoefficient': '0.07'}}


class AuditTests(unittest.TestCase):
    def test_actual_size_and_prices_do_not_become_directional_or_fee_approval(self):
        report, _ = inspect_market(market(), lambda url: metadata() if '/market/slug/' in url else book(), lambda: NOW)
        self.assertEqual(report['long_offers'][0], {'price': '0.65', 'quantity': '3'})
        self.assertFalse(report['side_mapping_verified'])
        self.assertFalse(report['fees_verified'])
        self.assertFalse(report['tradable_quote_approved'])
        self.assertNotIn('up_ask', report)

    def test_wrong_contract_and_invalid_books_cannot_supply_fills(self):
        mutations = [lambda b: b.update(marketSlug='other-contract'),
                     lambda b: b.update(offers=[]),
                     lambda b: b['offers'][0].update(qty='NaN'),
                     lambda b: b['offers'][0]['px'].update(currency='EUR'),
                     lambda b: b['bids'][0]['px'].update(value='.70'),
                     lambda b: b.update(bids=b['bids']*2)]
        for mutate in mutations:
            data = book()
            mutate(data['marketData'])
            with self.subTest(data=data), self.assertRaises((ValueError, ArithmeticError)):
                book_summary(data, 'exact-contract', NOW)

    def test_missing_stale_or_future_exchange_timestamp_is_not_fresh(self):
        for stamp in (None, iso(NOW-100), iso(NOW+1)):
            data = book()
            data['marketData']['transactTime'] = stamp
            self.assertFalse(book_summary(data, 'exact-contract', NOW)['timestamp_fresh'])

    def test_expiry_or_wrong_target_rejects_book(self):
        bad = metadata()
        bad['market']['assetPriceTerms']['priceToBeat']['value'] = '74000'
        calls = []
        def get(url):
            calls.append(url)
            return bad
        with self.assertRaisesRegex(ValueError, 'TERMS_MISMATCH'):
            inspect_market(market(), get, lambda: NOW)
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(ValueError, 'WINDOW_ROLLED'):
            inspect_market(market(), lambda url: metadata() if '/market/slug/' in url else book(), lambda: NOW+900)

    def test_rate_limit_persists_and_source_database_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'source.sqlite', Path(folder)/'audit'
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE records(kind TEXT, payload TEXT)')
                db.execute('INSERT INTO records VALUES (?,?)', ('market', json.dumps(market())))
            before = source.read_bytes()
            calls = []
            def get(url):
                calls.append(url)
                headers = Message()
                headers['Retry-After'] = '120'
                raise HTTPError(url, 429, 'rate limit', headers, None)
            result = audit(source, output, get=get, now=lambda: NOW, pause=lambda _: None)
            self.assertEqual(result['markets'][0]['http_status'], 429)
            again = audit(source, output, get=get, now=lambda: NOW+10)
            self.assertEqual(again['state'], 'RATE_LIMIT_COOLDOWN')
            self.assertEqual(len(calls), 1)
            self.assertEqual(before, source.read_bytes())
            self.assertEqual((output/'latest.json').stat().st_mode & 0o777, 0o600)
            self.assertFalse(result['real_trading'])
            self.assertEqual(result['simulated_orders_submitted'], 0)

if __name__ == '__main__':
    unittest.main()
