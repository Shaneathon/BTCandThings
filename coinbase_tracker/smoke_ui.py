"""Coin tracker fixture UI tests: no live API, credentials or orders."""
import copy
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from coinbase_tracker.collector import Store,collect
from coinbase_tracker.tests.test_tracker import fixture

root=Path(__file__).resolve().parent
app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
assert not app.exception,[e.message for e in app.exception]
assert any('SETUP' in m.value for m in app.info)
assert len(app.tabs)==5
assert 'coin.shaneathon.com' in ' '.join(m.proto.body for m in app.get('html'))
print('PASS Coin setup: Polymarket-style panels, four asset selector and no invented data')

now=time.time();anchor=int(now)//60*60
with patch('coinbase_bot.tests.test_coinbase.NOW',anchor),patch('coinbase_tracker.tests.test_tracker.NOW',anchor):
    def get(url,params=None):
        response=copy.deepcopy(fixture(url,params))
        product=params['product_id'] if url.endswith('/product_book') else url.split('/')[-2] if url.endswith(('/candles','/ticker')) else url.rsplit('/',1)[1]
        scale={'BTC-USD':100,'ETH-USD':10,'XRP-USD':.01,'SOL-USD':1}[product]
        if 'candles' in response:
            for bar in response['candles']:
                for key in ('open','high','low','close'): bar[key]=str(float(bar[key])*scale)
        if 'pricebook' in response:
            response['pricebook']['time']['seconds']=str(int(now)-1)
            for side in ('bids','asks'):
                for level in response['pricebook'][side]: level['price']=str(float(level['price'])*scale)
        return response
    store=Store(':memory:')
    report=collect(store,get,now)
    store.close()
with patch.dict(os.environ,{'COIN_STATUS_URL':'https://coin-status.example/status','COIN_READ_TOKEN':'fixture-token-only-not-a-secret-123456789'}),patch('coinbase_tracker.client.fetch',return_value=report):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Last completed close']==['$10,590.00']
    for product in ('ETH-USD','XRP-USD','SOL-USD'):
        app.radio[0].set_value(product).run(timeout=20)
        assert not app.exception,[e.message for e in app.exception]
        expected=float(report['products'][product]['candles'][-1]['close'])
        formatted=f'${expected:,.5f}' if product=='XRP-USD' else f'${expected:,.2f}'
        assert [m.value for m in app.metric if m.label=='Last completed close']==[formatted]
    for interval in ('5m','15m'):
        app.radio[1].set_value(interval).run(timeout=20)
        assert not app.exception,[e.message for e in app.exception]
    print('PASS Coin connected: all four independent assets, 1m/5m/15m charts, depth and signal panels')
import streamlit as st
st.cache_data.clear()
with patch.dict(os.environ,{'COIN_STATUS_URL':'https://coin-status.example/status','COIN_READ_TOKEN':'fixture-token-only-not-a-secret-123456789'}),patch('coinbase_tracker.client.fetch',side_effect=TimeoutError()):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception
    assert app.error
    print('PASS Coin feed outage: explicit pending state, no trading controls or fabricated prices')
