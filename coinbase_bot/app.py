"""Separate cbot.shaneathon.com read-only Coinbase paper dashboard."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from trading_bot.status_client import read_status
from coinbase_bot.market_data import PRODUCTS

st.set_page_config(page_title='CBot · Coinbase Paper',page_icon='◈',layout='wide')
st.html('''<style>.stApp{background:#091326;color:#e8efff}.block-container{max-width:1450px;padding-top:1.5rem}
.hero{padding:25px;border:1px solid #33568d;border-radius:18px;background:linear-gradient(115deg,#153d89,#111f3a);margin-bottom:20px}
.title{font-size:38px;font-weight:800;color:#f7faff}.sub{color:#b0c9ed}.kicker{color:#8ebcff;letter-spacing:2px;font-size:12px;font-weight:800}
[data-testid=stMetric]{background:#142643;padding:18px;border:1px solid #33568d;border-radius:14px}</style>''')
st.html('<div class="hero"><div class="kicker">CBOT · COINBASE SPOT · PAPER ONLY</div><div class="title">Crypto. A separate paper portfolio.</div><div class="sub">BTC / USD · ETH / USD · XRP / USD · SOL / USD</div></div>')
with st.sidebar:
    st.markdown('### CBot control room')
    st.caption('Target: cbot.shaneathon.com')
    st.success('Spot paper trading — no leverage or short selling')
    st.warning('Real Coinbase orders are disabled.')
    st.caption('PBot is the separate Polymarket bot at pbot.shaneathon.com. Wallets and API tokens are separate.')
    refresh=st.toggle('Refresh status every 10 seconds',value=True)
    if st.button('Refresh now'): st.rerun()


def setting(name):
    try: value=st.secrets.get(name,'')
    except Exception: value=''
    return str(value or os.environ.get(name,''))


@st.cache_data(ttl=5,show_spinner=False)
def load(url,token):
    return read_status(url,token,expected_venue='Coinbase Advanced')


def render():
    url,token=setting('CBOT_STATUS_URL'),setting('CBOT_READ_TOKEN')
    data={}
    if not url or not token:
        st.info('SETUP · Coinbase paper engine is not connected. No Coinbase account or trading key is required for public paper data.')
    else:
        try:
            data=load(url,token)
            if not 0<=time.time()-data.get('observed_at',0)<=120: st.warning('Coinbase paper status is stale.')
        except Exception as exc:
            st.error('Coinbase paper status unavailable ('+type(exc).__name__+').')
    account=data.get('account',{})
    positions=account.get('positions',[])
    tiles=st.columns(4)
    for col,label,key in zip(tiles[:3],('Virtual USD cash','Open cost basis','Realized paper P/L'),('cash','open_exposure','realized_pnl')):
        col.metric(label,f"${float(account[key]):,.2f}" if key in account else '—')
    tiles[3].metric('Open spot positions',len(positions) if data else '—')
    products,portfolio,journal,risk,live=st.tabs(['Coinbase markets','Spot portfolio','Decision journal','Strategy & risk','Live readiness'])
    with products:
        decisions={d['product_id']:d for d in data.get('decisions',[])}
        rows=[]
        for product in PRODUCTS:
            decision=decisions.get(product,{})
            signal=decision.get('signal',{})
            rows.append(dict(Product=product,Signal=signal.get('direction','PENDING'),
                             Decision=decision.get('action','WAITING FOR DATA'),Reason=decision.get('reason','—'),
                             EMA9=signal.get('ema9','—'),EMA21=signal.get('ema21','—')))
        st.dataframe(rows,hide_index=True,width='stretch')
        chosen=st.radio('Candle chart',PRODUCTS,horizontal=True)
        candles=data.get('market_candles',{}).get(chosen,[])
        if candles:
            from datetime import datetime,timezone
            st.line_chart([{'UTC':datetime.fromtimestamp(bar['start'],timezone.utc),'Close':float(bar['close'])} for bar in candles],x='UTC',y='Close')
            st.caption('Completed Coinbase one-minute closes. Stored separately from Polymarket price feeds.')
        else:
            st.info('Completed Coinbase candles will appear when the data feed is connected.')
        st.caption('Coinbase spot markets are continuous. They do not have Polymarket expiry countdowns or binary settlement targets.')
    with portfolio:
        if positions: st.dataframe(positions,hide_index=True,width='stretch')
        else: st.info('No paper crypto holdings yet.')
        if account.get('trades'): st.dataframe(account['trades'],hide_index=True,width='stretch')
        st.caption('No leverage or shorting. Paper buys use ask plus slippage; sells use bid minus slippage. Fees apply on both sides.')
        st.caption('Fills use sampled public quotes and assumed costs, not confirmed exchange executions. '
                   'Checks run about once a minute; stop-loss exits are simulated at an observed bid, not guaranteed prices. '
                   'All decisions and skips are retained in the separate paper ledger for review.')
    with journal:
        if data.get('decisions'): st.dataframe(data['decisions'],hide_index=True,width='stretch')
        else: st.info('Waiting for Coinbase data and paper decisions.')
    with risk:
        if data.get('configuration'): st.json(data['configuration'])
        else: st.info('Configuration will appear when the paper engine is connected.')
        st.caption('Experimental EMA9/21 plus 3-minute momentum. No historical profitability claim. Realized/cost-basis drawdown, not live mark-to-market.')
        st.caption('Stop loss/take profit are modeled decisions at polling time, not guaranteed exchange orders or fill prices.')
        st.code('touch /var/lib/cbot/STOP',language='bash')
        st.caption('With this path configured, the kill file blocks new entries; modeled risk exits remain active.')
    with live:
        st.warning('LIVE SUBMISSION UNAVAILABLE')
        st.caption('Coinbase order payload preparation exists. Account authorization, exchange permissions, order reconciliation and production execution remain future work.')
    if account.get('halted_reason'): st.error('Entry halt: '+account['halted_reason'])
    st.caption('Read-only dashboard. Paper research only. No Coinbase API trading credentials are loaded by this app.')


if refresh: st.fragment(run_every='10s')(render)()
else: render()
