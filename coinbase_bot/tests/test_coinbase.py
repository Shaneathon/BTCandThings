from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from coinbase_bot.market_data import fetch_all,fetch_product,PRODUCTS,BASE
from coinbase_bot.core import PaperBot,Config
from coinbase_bot.live import prepare_limit_order,submit,LiveTradingDisabled

NOW=1800000060


def public_fixture(url,params=None):
    if url.endswith('/product_book'):
        return {'pricebook':{'product_id':params['product_id'],'time':{'seconds':str(NOW-1),'nanos':0},
                            'bids':[{'price':'105.9','size':'10'}],'asks':[{'price':'106','size':'10'}]}}
    if url.endswith('/candles'):
        return {'candles':[{'start':str(NOW-3600+i*60),'open':str(100+i*.1),'high':str(100.2+i*.1),
                'low':str(99.8+i*.1),'close':str(100+i*.1),'volume':'100'} for i in range(61)]}
    product=url.rsplit('/',1)[1]
    return dict(product_id=product,product_type='SPOT',base_currency_id=product.split('-')[0],quote_currency_id='USD',
                status='online',trading_disabled=False,base_increment='.0001',quote_increment='.01',base_min_size='.0001',quote_min_size='1')


class CoinbaseTests(unittest.TestCase):
    def test_completed_candles_and_exact_public_products(self):
        snapshots=fetch_all(NOW,public_fixture)
        self.assertEqual(set(snapshots),set(PRODUCTS))
        self.assertTrue(all(len(s['candles'])==60 for s in snapshots.values()))
        self.assertTrue(all(s['candles'][-1]['start']+60<=NOW for s in snapshots.values()))

    def test_product_outage_does_not_block_others(self):
        def get(url,params=None):
            if '/ETH-USD' in url: raise TimeoutError()
            return public_fixture(url,params)
        result=fetch_all(NOW,get)
        self.assertIn('error',result['ETH-USD'])
        self.assertNotIn('error',result['BTC-USD'])

    def test_identity_gaps_future_and_crossed_book_rejected(self):
        for mode in ('identity','gaps','future','crossed','disabled'):
            def get(url,params=None):
                response=public_fixture(url,params)
                if mode=='identity' and 'product_id' in response: response['product_id']='ETH-USD'
                if mode=='disabled' and 'trading_disabled' in response: response['trading_disabled']=True
                if mode=='gaps' and 'candles' in response: response['candles'].pop(10)
                if mode=='future' and 'pricebook' in response: response['pricebook']['time']['seconds']=str(NOW+10)
                if mode=='crossed' and 'pricebook' in response: response['pricebook']['bids'][0]['price']='107'
                return response
            with self.subTest(mode=mode),self.assertRaises(ValueError): fetch_product('BTC-USD',NOW,get)

    def test_buy_sell_fees_and_restart_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'coinbase.sqlite'
            bot=PaperBot(path)
            source={'BTC-USD':fetch_product('BTC-USD',NOW,public_fixture)}
            report=bot.cycle(source,NOW)
            self.assertEqual(len(report['account']['positions']),1)
            self.assertEqual(report['account']['venue'],'Coinbase Advanced')
            cash=report['account']['cash']
            position=report['account']['positions'][0]
            bot.close()
            bot=PaperBot(path)
            again=bot.cycle(source,NOW+1)
            self.assertEqual(again['account']['cash'],cash)
            source['BTC-USD'].update(bid='100',ask='100.1',observed_at=NOW+2,book_time=NOW+2)
            closed=bot.cycle(source,NOW+2,kill_switch=True)
            self.assertFalse(closed['account']['positions'])
            self.assertEqual(closed['decisions'][0]['action'],'PAPER_SELL')
            expected=Decimal(position['quantity'])*Decimal('100')*(1-Decimal('.0005'))*(1-Decimal('.006'))-Decimal(position['cost'])
            self.assertEqual(Decimal(closed['account']['realized_pnl']),expected)
            twice=bot.cycle(source,NOW+3,kill_switch=True)
            self.assertEqual(twice['account']['cash'],closed['account']['cash'])
            bot.close()

    def test_kill_stale_and_liquidity_checks(self):
        for mode in ('kill','stale','depth'):
            bot=PaperBot(':memory:')
            source={'BTC-USD':fetch_product('BTC-USD',NOW,public_fixture)}
            if mode=='stale': source['BTC-USD']['book_time']=NOW-16
            if mode=='depth': source['BTC-USD']['ask_size']='.00000001'
            report=bot.cycle(source,NOW,kill_switch=mode=='kill')
            self.assertFalse(report['account']['positions'])
            bot.close()

    def test_risk_increments_and_no_shorting(self):
        bot=PaperBot(':memory:')
        report=bot.cycle(fetch_all(NOW,public_fixture),NOW)
        self.assertLessEqual(Decimal(report['account']['open_exposure']),Decimal(Config().max_daily_loss))
        self.assertLessEqual(Decimal(report['account']['open_exposure']),Decimal(Config().max_exposure))
        for p in report['account']['positions']:
            self.assertEqual(Decimal(p['quantity'])%Decimal('.0001'),0)
            self.assertGreater(Decimal(p['quantity']),0)
        self.assertFalse(report['account']['live_orders_enabled'])
        bot.close()

    def test_foreign_wallet_rejected_without_changes(self):
        from trading_bot.core import PaperBot as PolymarketBot
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'polymarket.sqlite'
            pbot=PolymarketBot(path); pbot.close()
            before=path.read_bytes()
            with self.assertRaises(ValueError): PaperBot(path)
            self.assertEqual(path.read_bytes(),before)

    def test_status_reader_cannot_swap_bot_venues(self):
        from io import BytesIO
        import json
        from unittest.mock import patch,Mock
        from trading_bot.status_client import read_status
        payload=json.dumps({'account':{'mode':'PAPER','venue':'Coinbase Advanced','live_orders_enabled':False}}).encode()
        opener=Mock()
        opener.open.side_effect=lambda *args,**kwargs: BytesIO(payload)
        with patch('trading_bot.status_client.build_opener',return_value=opener):
            with self.assertRaises(ValueError): read_status('https://example.com/status','x'*32)
            result=read_status('https://example.com/status','x'*32,expected_venue='Coinbase Advanced')
            self.assertEqual(result['account']['venue'],'Coinbase Advanced')

    def test_live_submission_disabled(self):
        request=prepare_limit_order('BTC-USD','BUY','.001','60000','durable-example-id')
        self.assertEqual(request['product_id'],'BTC-USD')
        self.assertIn('limit_limit_gtc',request['order_configuration'])
        with self.assertRaises(LiveTradingDisabled): submit(request)
        with self.assertRaises(ValueError): prepare_limit_order('BTC-USD','SHORT','1','60000','id')


if __name__=='__main__': unittest.main()
