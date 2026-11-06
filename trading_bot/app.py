"""Independent pbot.shaneathon.com frontend. Read-only; no order submission."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from trading_bot.core import STREAMS
from trading_bot.status_client import read_status

st.set_page_config(page_title='PBot · Paper Trading',page_icon='◈',layout='wide')
st.html('''<style>
.stApp{background:#09121e;color:#e5edf7}.block-container{max-width:1500px;padding-top:1.5rem}
h1,h2,h3{letter-spacing:-.03em}.hero{padding:25px;border:1px solid #29445a;border-radius:18px;background:linear-gradient(120deg,#123342,#111d31);margin-bottom:20px}
.kicker{font-size:12px;color:#67e8c0;letter-spacing:2px;font-weight:800}.title{font-size:38px;font-weight:800;color:#f4f9ff}
.subtitle{color:#9cb4c7;font-size:14px;margin-top:6px}.badge{float:right;padding:6px 12px;border:1px solid #4bbf9b;border-radius:20px;color:#8af2c9;font-size:12px}
[data-testid=stMetric]{background:#132235;padding:18px;border:1px solid #29445a;border-radius:14px}[data-testid=stMetricValue]{color:#f2f8ff}
[data-testid=stTabs] button{font-weight:700}
</style>''')
st.html('<div class="hero"><span class="badge">PAPER ONLY</span><div class="kicker">PBOT · INDEPENDENT TRADING TERMINAL</div><div class="title">Ten markets. One paper portfolio.</div><div class="subtitle">BTC · ETH · XRP · SOL · Gold · Silver — separate from the BTCandThings tracker</div></div>')
with st.sidebar:
    st.markdown('### PBot control room')
    st.caption('Target hostname: pbot.shaneathon.com')
    st.success('Paper trading mode')
    st.warning('Live submission is disabled in this release.')
    st.caption('This dashboard is read-only. Strategy and risk configuration live on the paper engine server.')
    refresh=st.toggle('Refresh status every 10 seconds',value=True)
    if st.button('Refresh now'):
        st.rerun()


def setting(name):
    try:
        value=st.secrets.get(name,'')
    except Exception:
        value=''
    return str(value or os.environ.get(name,''))


@st.cache_data(ttl=5,show_spinner=False)
def status(url,token):
    return read_status(url,token)


def content():
    url,token=setting('PBOT_STATUS_URL'),setting('PBOT_READ_TOKEN')
    data={}
    if not url or not token:
        st.info('SETUP · Paper engine not connected yet. No trades or performance results are being invented.')
    else:
        try:
            data=status(url,token)
            age=time.time()-data.get('observed_at',0)
            if not 0<=age<=30:
                st.warning('Paper engine status is stale. Displayed positions may be out of date.')
        except Exception as exc:
            st.error(f'Paper status unavailable ({type(exc).__name__}). No account credentials are displayed.')
    account=data.get('account',{})
    if data.get('operation_mode') == 'OBSERVE_ONLY':
        st.warning('OBSERVATION ONLY · Paper entries are paused while quote mapping is verified. Live trading is disabled.')
        st.caption(f"Research input: {data.get('input_status', 'UNKNOWN')} · "
                   f"{data.get('input_markets', 0)} archived markets · "
                   f"{data.get('input_predictions', 0)} prediction snapshots. "
                   "The displayed balance is virtual money.")
    positions=account.get('positions',[])
    opened=[p for p in positions if p['state']=='PAPER_OPEN']
    columns=st.columns(4)
    def money(key):
        return f"${float(account[key]):,.2f}" if key in account else '—'
    columns[0].metric('Virtual cash',money('cash'))
    columns[1].metric('Open capital committed',money('open_exposure'))
    columns[2].metric('Realized paper P/L',money('realized_pnl'))
    columns[3].metric('Open paper positions',len(opened) if data else '—')
    if account.get('halted_reason'):
        st.error('New entries halted: '+account['halted_reason'])
    markets,portfolio,decisions,risk,live=st.tabs(['10 markets','Paper portfolio','Decision journal','Strategy & risk','Live readiness'])
    with markets:
        st.markdown('### Market coverage')
        rows=[]
        latest={(d.get('asset'),d.get('duration_seconds')):d for d in data.get('decisions',[])}
        for asset,seconds in sorted(STREAMS):
            decision=latest.get((asset,seconds),{})
            score=decision.get('history',{})
            rows.append({'Asset':asset,'Market':f'{seconds//60}m',
                'Open positions':sum(p['asset']==asset and p['duration_seconds']==seconds for p in opened),
                'Decision':decision.get('action','WAITING FOR DATA'),'Reason':decision.get('reason','—'),
                'Historical markets':score.get('markets','—')})
        st.dataframe(rows,hide_index=True,width='stretch')
        st.caption('Crypto: 5m + 15m. Gold/silver: 15m. No unsupported 5m metals streams.')
    with portfolio:
        st.markdown('### Persistent paper ledger')
        if positions:
            st.dataframe(positions,hide_index=True,width='stretch')
        else:
            st.info('No paper positions yet. Positions open only when data, history, quotes and risk checks pass.')
        st.caption('Equity and drawdown use realized/cost-basis accounting, not live bid marks. Settlements use verified official outcomes.')
    with decisions:
        if data.get('decisions'):
            st.dataframe(data['decisions'],hide_index=True,width='stretch')
        else:
            st.info('Decision records will appear after the engine processes collected data.')
        st.caption('Each entry and skipped opportunity is recorded. The server retains the full decision journal; this panel shows its latest cycle.')
    with risk:
        config=data.get('configuration')
        if config:
            st.json(config)
        else:
            st.info('Risk configuration will appear after the paper engine is connected.')
        st.markdown('Entry checks include per-market historical scores, net modeled edge after costs, fresh mapped quotes, spread, available size, cash and exposure limits.')
        st.caption('Initial example settings are research assumptions, not optimized parameters or a verified fee schedule. Paper success never enables live trading automatically.')
        st.code('touch /var/lib/btcandthings-bot/STOP',language='bash')
        st.caption('With that kill-file path configured on the server, the command pauses new paper entries. Existing paper settlements continue.')
    with live:
        st.warning('LIVE ORDERS DISABLED · No real account is connected.')
        st.markdown('The live module prepares contract-mapped limit-order payloads and an explicit SDK preview interface. Submission is unavailable.')
        st.caption('A later live release needs explicit authorization, authenticated account checks, order/fill reconciliation, duplicate-order protection, exchange limits and live risk controls.')
    st.caption('Paper research only. This app contains no trade buttons and cannot submit orders.')


if refresh:
    st.fragment(run_every='10s')(content)()
else:
    content()
