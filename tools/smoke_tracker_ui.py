"""Streamlit fixture smoke tests; run with the website requirements installed.

Exercises the shared workspace, not the separate legacy BTC 15m application.
No external requests, database writes, or trading calls.
"""
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
APP_PATH = str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload')

SCRIPT = '''
import sys
sys.path.insert(0, APP_PATH)
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone
from market_workspace import render_workspace, ASSETS
asset = ASSET_VALUE
duration = DURATION_VALUE
now = 7260
start = 7200
seconds = 300 if duration == '5m' else 900
scale = {'BTC':100,'ETH':10,'XRP':.01,'SOL':1,'GOLD':20,'SILVER':.2}[asset]
def discover(slug):
    return {'slug':slug}, {'slug':slug+'-contract'}, []
def full_market(slug):
    return {'slug':slug, 'assetPriceTerms': {'asset':{'symbol':asset.lower()},
       'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
       'windowStart':datetime.fromtimestamp(start,timezone.utc).isoformat(),
       'windowEnd':datetime.fromtimestamp(start+seconds,timezone.utc).isoformat(),
       'priceToBeat':{'value':120*scale,'currency':'USD'}}}
def get_json(url,params):
    if 'yahoo' in url:
        return {'chart':{'result':[{'timestamp':[1260+i*60 for i in range(101)],
          'indicators':{'quote':[{'open':[(100+i*.2)*scale for i in range(101)],
          'high':[(101+i*.2)*scale for i in range(101)],
          'low':[(99+i*.2)*scale for i in range(101)],
          'close':[(100.5+i*.2)*scale for i in range(101)], 'volume':[10]*101}]}}]}}
    return {'error':[], 'result':{params['pair']:[
       [1260+i*60,(100+i*.2)*scale,(101+i*.2)*scale,(99+i*.2)*scale,(100.5+i*.2)*scale,100*scale,10,1]
       for i in range(101)],'last':7260}}
render_workspace(st,components,asset,duration,now,discover,full_market,get_json)
'''
for asset in ('BTC','ETH','XRP','SOL','GOLD','SILVER'):
    for duration in ('5m','15m'):
        script=SCRIPT.replace('APP_PATH',repr(APP_PATH)).replace('ASSET_VALUE',repr(asset)).replace('DURATION_VALUE',repr(duration))
        app=AppTest.from_string(script).run(timeout=15)
        assert not app.exception, [(e.message,e.stack_trace) for e in app.exception]
        assert [tab.label for tab in app.tabs] == ['Trading','Performance','Advanced · Research & Diagnostics']
        probabilities=[m.value for m in app.metric if m.label.startswith('Forecast: finish')]
        if asset in ('GOLD','SILVER') and duration == '5m':
            assert not probabilities
            assert app.warning
        else:
            assert len(probabilities)==2, [(m.label,m.value) for m in app.metric]
            assert abs(sum(float(v.rstrip('%')) for v in probabilities)-100)<.11
        timer=app.get('iframe')[0].proto.srcdoc
        assert f'{asset} {duration} WINDOW' in timer
        assert str(7200+(300 if duration=='5m' else 900)) in timer
        app.radio[0].set_value('5m').run(timeout=15)
        assert not app.exception
        print(f'PASS {asset} {duration}: render, market-aware countdown, signal state, tabs, chart switch')
# Wrong-asset contract must leave the forecast paused.
script=SCRIPT.replace('APP_PATH',repr(APP_PATH)).replace('ASSET_VALUE',repr('ETH')).replace('DURATION_VALUE',repr('5m')).replace("{'symbol':asset.lower()}","{'symbol':'btc'}")
app=AppTest.from_string(script).run(timeout=15)
assert not app.exception
assert not [m for m in app.metric if m.label.startswith('Forecast: finish')]
print('PASS mismatched-asset contract pauses forecast')
