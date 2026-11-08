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
assert [t.label for t in app.tabs]==['8 markets','Paper portfolio','Decision journal','Strategy & risk','Live readiness']
assert len(app.dataframe[0].value)==8
assert any('SETUP' in item.value for item in app.info)
app.toggle[0].set_value(False).run(timeout=20)
assert not app.exception
print('PASS PBot setup dashboard: eight crypto streams, five tabs, refresh switch, no invented balances')

bot=PaperBot(':memory:',replace(Config(),minimum_settled_markets=2))
report=bot.cycle(*fixtures(),NOW)
bot.close()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=report):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Open paper positions']==['8']
    assert [m.value for m in app.metric if m.label=='Virtual cash']==['$920.96']
    assert len(app.dataframe[0].value)==8
    assert len(app.dataframe[1].value)==8
    assert all('buy' not in b.label.lower() and 'trade' not in b.label.lower() for b in app.button)
    print('PASS PBot connected fixture: virtual wallet, eight positions, decision journal, no trade controls')
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
    dual['new_fixed_price_entries_paused']=True
    for bot in bots.values(): bot.close()
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=dual):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('Hypothetical fixed prices' in w.value for w in app.warning)
    assert any('New fixed-price entries are paused' in i.value for i in app.info)
    totals=next(frame.value for frame in app.dataframe if 'wallet' in frame.value.columns)
    assert set(totals['wallet'])=={'Champion','Challenger B'}
    assert 'realized_net_pnl' in totals.columns
    assert len([m for m in app.metric if m.label=='Hypothetical realized P/L'])==2
    assert any('Automatic paper-trade reviews' in e.label for e in app.expander)
    print('PASS PBot dual directional sandbox: separate wallets, assumed-price warning, automatic reviews')

from trading_bot.dual_sandbox import MarketSandboxConfig, RESEARCH_MODEL, run_market_cycles
from trading_bot.tests.test_bot import iso
with tempfile.TemporaryDirectory() as temporary:
    research_bots={name:Sandbox(Path(temporary)/(name+'.sqlite'),MarketSandboxConfig(asset=asset,duration_seconds=900,model_version=RESEARCH_MODEL))
                   for name,asset in [('ETH_15m','ETH'),('XRP_15m','XRP')]}
    inputs=dual_fixture()
    inputs['markets'][0]['asset']='ETH'
    inputs['markets'][0]['market_slug']='eth-updown-15m-fixture'
    inputs['markets'][0]['contract_slug']='eth-fixture-contract'
    inputs['predictions']=[dict(market_slug=inputs['markets'][0]['market_slug'],recorded_at=iso(DUAL_NOW-2),
                                source_timestamp=iso(DUAL_NOW-5),model_version=RESEARCH_MODEL,predicted_up_probability=.2)]
    dual['market_portfolios']=run_market_cycles(research_bots,inputs,DUAL_NOW)
    for bot in research_bots.values(): bot.close()
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=dual):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert app.selectbox[0].label=='Inspect a research market'
    coverage=next(frame.value for frame in app.dataframe if 'Market' in frame.value.columns and 'State' in frame.value.columns)
    assert set(coverage['Market'])=={'ETH_15m','XRP_15m'}
    assert 'PAUSED_METADATA_UNAVAILABLE' in coverage['State'].tolist()
    print('PASS PBot all-market panel: independent research wallets and explicit paused feed')

# The new execution dashboard must keep the fixed-price histories separate.
from trading_bot.observed_paper import Engine as ObservedEngine
with tempfile.TemporaryDirectory() as temporary:
    engine=ObservedEngine(Path(temporary)/'observed.sqlite')
    observed=engine.report(DUAL_NOW,True)
    engine.close()
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}), patch('trading_bot.status_client.read_status',return_value=observed):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('OBSERVED-BOOK PAPER' in item.value for item in app.info)
    table=next(frame.value for frame in app.dataframe if 'reserved_cash' in frame.value.columns)
    assert len(table)==10
    assert all(value=='0' for value in table['realized_net_pnl'])
    print('PASS PBot observed execution: 10 active wallets, zero inherited artificial profit')

# Click-through views and Central last-trade times retain the original overview.
import copy,time
from trading_bot.display_status import central
click_data=copy.deepcopy(observed);current=time.time()
click_data['observed_at']=current
click_data['display_health']=dict(engine_updated_at=current,input_updated_at=current-1,input_fresh=True,input_error=None,
                                 last_filled_at=current-600,last_settled_at=current-500)
for name,state in click_data['portfolios'].items():
    state['activity']=dict(last_filled_at=None,last_settled_at=None,last_order_proposed_at=None,filled_trade_count=0)
    state['display_state']=dict(state='WAITING_FOR_ENTRY_WINDOW',severity='info')
eth=click_data['portfolios']['ETH_5m']
eth['account'].update(cash='998.75',realized_pnl='-1.25')
eth['activity'].update(last_filled_at=current-600,last_settled_at=current-500,filled_trade_count=1)
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=click_data):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    table=next(frame.value for frame in app.dataframe if 'reserved_cash' in frame.value.columns)
    assert len(table)==10
    assert 'last_trade_central' in table.columns
    selector=next(r for r in app.radio if r.label=='Click a market or model')
    selector.set_value('ETH_5m').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Wallet virtual cash · all history']==['$998.75']
    assert [m.value for m in app.metric if m.label=='Wallet realized paper P/L']==['$-1.25']
    assert any(central(current-600) in m.value for m in app.markdown)
    assert any('FIRST recorded' in c.value for c in app.caption)
    print('PASS PBot clickable wallets: overview retained, selected P/L and Central trade time shown, historical skips labeled')

# Last trade details and the optional complete-history browser are explicit.
from trading_bot.trade_history import trade_row
last=trade_row('ETH_5m',dict(market_slug='eth-last-filled-fixture',asset='ETH',duration_seconds=300,model_version='fixture',
    side='UP',quantity='5',entry_price='.24',fees='.05',cost='1.25',state='PAPER_CLOSED',payout='0',pnl='-1.25',
    opened_at=current-600,closed_at=current-500,window_start=current-900,window_end=current-600),
    'FILLED',dict(plan=dict(quantity='5')))
click_data['portfolios']['ETH_5m']['activity']['last_trade']=last

def history_fixture(url,token,wallet='*',page=1,as_of=None):
    return dict(account=dict(mode='PAPER',venue='Polymarket US',live_orders_enabled=False),wallet=wallet,
                as_of=as_of,page=1,page_count=1,page_size=50,total_filled_trades=1,trades=[last])
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=click_data),patch('trading_bot.status_client.read_trades',side_effect=history_fixture):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    next(r for r in app.radio if r.label=='Click a market or model').set_value('ETH_5m').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('eth-last-filled-fixture' in m.value for m in app.markdown)
    next(c for c in app.checkbox if c.label=='Show complete trade history').set_value(True).run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    history_table=next(f.value for f in app.dataframe if 'Average entry ($)' in f.value.columns)
    assert history_table.iloc[0]['Result']=='LOST'
    assert history_table.iloc[0]['Net P/L ($)']=='-1.25'
    assert any('Entry target and maximum: $1.50' in c.value for c in app.caption)
    print('PASS PBot trade detail/history: last fill description, outcome/fees, complete-history control and $1.50 maximum entry target')

# A guard pause is distinct from a frozen engine and includes Central expiry.
click_data['automatic_review']=dict(reviewed_at=current,wallets=[dict(wallet='ETH_5m',status='PAUSED_NEW',closed_trades=10,net_pnl='-20',entry_pause=dict(paused_until=current+21600))])
click_data['portfolios']['ETH_5m']['automatic_entry_pause']=dict(paused_until=current+21600,reason='Hourly paper loss guard fixture')
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=click_data):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    next(r for r in app.radio if r.label=='Click a market or model').set_value('ETH_5m').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('Automatic entry pause until '+central(current+21600) in w.value for w in app.warning)
    assert any(e.label=='Hourly paper review and automatic entry pauses' for e in app.expander)
    print('PASS hourly paper guard: review results and Central pause expiry shown without live controls')

# Performance selector defaults to current tagged entries, without resetting cash.
from trading_bot.performance_periods import breakdown,CURRENT
for name,r in click_data['portfolios'].items():
    market=r['account']['market_pnl'][0]
    r['performance_periods']=breakdown([],streams=[(market['asset'],market['duration_seconds'])])
old=dict(market_slug='old-profit',asset='ETH',duration_seconds=300,state='PAPER_CLOSED',cost='1',fees='0',payout='11',pnl='10')
new=dict(old,market_slug='new-loss',cost='2',payout='0',pnl='-2',entry_limits=dict(version=CURRENT))
click_data['portfolios']['ETH_5m']['performance_periods']=breakdown([old,new],streams=[('ETH',300)])
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=click_data):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    next(r for r in app.radio if r.label=='Click a market or model').set_value('ETH_5m').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Wallet realized paper P/L']==['$-2.00']
    assert [m.value for m in app.metric if m.label=='Wallet virtual cash · all history']==['$998.75']
    next(r for r in app.radio if r.label=='Performance results').set_value('Earlier entries').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert [m.value for m in app.metric if m.label=='Wallet realized paper P/L']==['$10.00']
    next(r for r in app.radio if r.label=='Performance results').set_value('All history').run(timeout=20)
    assert [m.value for m in app.metric if m.label=='Wallet realized paper P/L']==['$8.00']
    print('PASS policy performance selector: current/earlier/all totals separate; actual wallet cash preserved')

# Probability trailing and pending sell status are explicit, not market-price stops.
click_data['portfolios']['ETH_5m']['probability_trails']=[dict(entry_key='eth-fixture',peak='.72',current='.67',signal_at=current,triggered_at=current)]
click_data['portfolios']['ETH_5m']['exit_order_states']={'PROPOSED':1}
click_data['portfolios']['ETH_5m']['display_state']=dict(state='EXIT_ORDER_PENDING',severity='info')
st.cache_data.clear()
with patch.dict('os.environ',{'PBOT_STATUS_URL':'https://status.example/status','PBOT_READ_TOKEN':'synthetic-token-not-a-secret-123456789'}),patch('trading_bot.status_client.read_status',return_value=click_data):
    app=AppTest.from_file(str(root/'app.py')).run(timeout=20)
    next(r for r in app.radio if r.label=='Click a market or model').set_value('ETH_5m').run(timeout=20)
    assert not app.exception,[e.message for e in app.exception]
    assert any('Trailing exit awaiting' in i.value for i in app.info)
    trail=next(f.value for f in app.dataframe if 'Peak model probability' in f.value.columns)
    assert trail.iloc[0]['Peak model probability']=='72.0%'
    assert trail.iloc[0]['5-point trailing level']=='67.0%'
    print('PASS probability trailing display: model peak/current/5-point level and pending bid-exit status')
