"""CBot dashboard fixture checks. No Coinbase account, requests or orders."""
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from coinbase_bot.core import PaperBot
from coinbase_bot.market_data import fetch_all
from coinbase_bot.tests.test_coinbase import public_fixture,NOW

root=Path(__file__).resolve().parent
app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
assert not app.exception
assert len(app.dataframe[0].value)==4
assert any('SETUP' in item.value for item in app.info)
assert 'cbot.shaneathon.com' in ' '.join(item.value for item in app.caption)
print('PASS CBot setup: four Coinbase products and separate hostname')
bot=PaperBot(':memory:')
report=bot.cycle(fetch_all(NOW,public_fixture),NOW)
bot.close()
with patch.dict('os.environ',{'CBOT_STATUS_URL':'https://cbot-status.example/status','CBOT_READ_TOKEN':'test-only-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=report):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Open spot positions']==[str(len(report['account']['positions']))]
    assert len(app.tabs)==5
    assert all('buy' not in b.label.lower() and 'trade' not in b.label.lower() for b in app.button)
    print('PASS CBot connected fixture: spot wallet, positions, risk tabs, no trade controls')
import streamlit as st
st.cache_data.clear()
with patch.dict('os.environ',{'CBOT_STATUS_URL':'https://cbot-status.example/status','CBOT_READ_TOKEN':'test-only-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',side_effect=TimeoutError()):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception
    assert app.error
    print('PASS CBot outage: explicit unavailable state')

# New mode exposes fee uncertainty and independent per-product accounting.
from coinbase_bot.observed import ObservedBot
observed_bot=ObservedBot(':memory:')
observed_report=observed_bot.cycle({},NOW)
observed_bot.close()
st.cache_data.clear()
with patch.dict('os.environ',{'CBOT_STATUS_URL':'https://status.example/status','CBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=observed_report):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('OBSERVED LIMIT PAPER' in item.value for item in app.info)
    assert any('Fees are estimated' in item.value for item in app.warning)
    assert any('realized_net_pnl' in frame.value.columns and len(frame.value)==4 for frame in app.dataframe)
    print('PASS CBot observed mode: explicit estimated fees and per-product new-ledger P/L')
