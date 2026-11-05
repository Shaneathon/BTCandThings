"""Fixture-only checks for the separate PBot dashboard; no network or orders."""
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from trading_bot.core import PaperBot,Config
from trading_bot.tests.test_bot import fixtures,NOW
from dataclasses import replace

root=Path(__file__).resolve().parent
app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
assert not app.exception,[e.message for e in app.exception]
assert [t.label for t in app.tabs]==['10 markets','Paper portfolio','Decision journal','Strategy & risk','Live readiness']
assert len(app.dataframe[0].value)==10
assert any('SETUP' in item.value for item in app.info)
app.toggle[0].set_value(False).run(timeout=20)
assert not app.exception
print('PASS PBot setup dashboard: ten streams, five tabs, refresh switch, no invented balances')

bot=PaperBot(':memory:',replace(Config(),minimum_settled_markets=2))
report=bot.cycle(*fixtures(),NOW)
bot.close()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=report):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Open paper positions']==['10']
    assert [m.value for m in app.metric if m.label=='Virtual cash']==['$901.20']
    assert len(app.dataframe[0].value)==10
    assert len(app.dataframe[1].value)==10
    assert all('buy' not in b.label.lower() and 'trade' not in b.label.lower() for b in app.button)
    print('PASS PBot connected fixture: virtual wallet, ten positions, decision journal, no trade controls')
import streamlit as st
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',side_effect=TimeoutError()):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception
    assert app.error
    print('PASS PBot API outage: explicit unavailable state without fabricated account data')
