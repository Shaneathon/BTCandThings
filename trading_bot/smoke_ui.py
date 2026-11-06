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
paused = dict(report, operation_mode='OBSERVE_ONLY', paper_entries_enabled=False,
              input_status='FRESH', input_markets=10, input_predictions=100)
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=paused):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception
    assert any('OBSERVATION ONLY' in w.value for w in app.warning)
    assert any('100 prediction snapshots' in c.value for c in app.caption)
    print('PASS PBot observation mode: entry pause and research provenance visible')
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',side_effect=TimeoutError()):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception
    assert app.error
    print('PASS PBot API outage: explicit unavailable state without fabricated account data')

# The directional experiment must never present its assumed prices as real fills.
import tempfile
from trading_bot.dual_sandbox import Sandbox, SandboxConfig, MODELS, run_cycle
from trading_bot.tests.test_dual_sandbox import fixture as dual_fixture, NOW as DUAL_NOW
with tempfile.TemporaryDirectory() as temporary:
    bots={name:Sandbox(Path(temporary)/(name+'.sqlite'),SandboxConfig(model_version=model)) for name,model in MODELS.items()}
    dual=run_cycle(bots,dual_fixture(),DUAL_NOW)
    for bot in bots.values(): bot.close()
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=dual):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('Hypothetical fixed prices' in w.value for w in app.warning)
    assert len([m for m in app.metric if m.label=='Hypothetical realized P/L'])==2
    assert any('Automatic paper-trade reviews' in e.label for e in app.expander)
    print('PASS PBot dual directional sandbox: separate wallets, assumed-price warning, automatic reviews')
