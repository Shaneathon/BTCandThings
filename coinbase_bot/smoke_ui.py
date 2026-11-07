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

# Forward comparison is separate, explicitly small-sample and baseline-preserving.
from coinbase_bot.fee_filter import FeeFilterBot
from coinbase_bot.comparison import compare
import tempfile
with tempfile.TemporaryDirectory() as folder:
    a,b=Path(folder)/'observed-v1.sqlite',Path(folder)/'fee-filter-v1.sqlite'
    base=ObservedBot(a);child=FeeFilterBot(b)
    base_report=base.cycle({},NOW);child.cycle({},NOW)
    base.close();child.close()
    base_report['paper_comparison']=compare(a,b,NOW+1)
    st.cache_data.clear()
    with patch.dict('os.environ',{'CBOT_STATUS_URL':'https://status.example/status','CBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=base_report):
        app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
        assert not app.exception,[e.message for e in app.exception]
        assert any('Forward paper comparison' in h.value for h in app.markdown)
        assert any('INSUFFICIENT_FORWARD_TRADES' in c.value for c in app.caption)
        table=next(frame.value for frame in app.dataframe if 'experiment' in frame.value.columns)
        assert set(table['experiment'])=={'Baseline','Fee filter V1'}
        print('PASS CBot forward experiment comparison: aligned period, separate rows, small-sample label')

# Selecting a coin changes the actual isolated wallet figures, not just candles.
import copy
from coinbase_bot.product_wallets import aggregate as combine_wallets
wallets={}
for product,cash,pnl in [('BTC-USD','245','-5'),('ETH-USD','252','2'),('XRP-USD','250','0'),('SOL-USD','250','0')]:
    wallet=copy.deepcopy(observed_report)
    wallet['selected_product']=product;wallet['wallet_initial_allocation']='250'
    wallet['account'].update(cash=cash,realized_pnl=pnl,open_exposure='0',positions=[],trades=[])
    wallet['market_pnl']=[row for row in wallet['market_pnl'] if row['product_id']==product]
    wallet['decisions']=[row for row in wallet['decisions'] if row['product_id']==product]
    wallets[product]=wallet
isolated=combine_wallets(wallets,'baseline',NOW)
with patch.dict('os.environ',{'CBOT_STATUS_URL':'https://status.example/status','CBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=isolated):
    st.cache_data.clear()
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Virtual USD cash']==['$245.00']
    assert [m.value for m in app.metric if m.label=='Realized paper P/L']==['$-5.00']
    chooser=next(r for r in app.radio if r.label=='Crypto')
    chooser.set_value('ETH-USD').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Virtual USD cash']==['$252.00']
    assert [m.value for m in app.metric if m.label=='Realized paper P/L']==['$2.00']
    assert not any(r.label=='Candle chart' for r in app.radio)
    print('PASS CBot isolated selector: balances/P&L switch together, no pooled cash or conflicting chart selector')
