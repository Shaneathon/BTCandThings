"""coin.shaneathon.com: BTC-style design, Coinbase continuous spot data."""
import os
from pathlib import Path
import sys
import time
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'BTCandThings_Website'/'BTCandThings_Upload'))
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from market_candles import candle_svg
from tracker_panels import signal_card
from coinbase_tracker.client import fetch
from coinbase_bot.market_data import PRODUCTS

NAMES={'BTC-USD':'Bitcoin','ETH-USD':'Ethereum','XRP-USD':'XRP','SOL-USD':'Solana'}
st.set_page_config(page_title='Coin · Coinbase Market Tracker',page_icon='◈',layout='wide')
st.html('''<style>
.stApp{background:#0b1120;color:#e2e8f0}.block-container{max-width:1700px;padding:.6rem 1rem 2rem}
h1,h2,h3{letter-spacing:-.025em}.masthead{background:linear-gradient(105deg,#13263e,#0f192b);border:1px solid #2a405b;border-radius:10px;padding:12px 16px;margin-bottom:10px}
.kicker{font-size:11px;letter-spacing:1.6px;color:#38bdf8;font-weight:700}.title{font-size:25px;font-weight:800;color:#f8fafc}.sub{color:#94a3b8;font-size:12px}
[data-testid=stMetric]{background:#151f32;border:1px solid #29384e;border-radius:10px;padding:9px 13px}[data-testid=stMetricValue]{font-size:1.3rem;color:#f8fafc}
.signal-card{min-height:115px;background:linear-gradient(125deg,#13243b,#0d192a);border:1px solid #334b66;border-radius:10px;padding:12px 15px;margin:3px 0 8px}
.signal-card.up{border-color:#22c55e}.signal-card.down{border-color:#ef4444}.signal-card.neutral{border-color:#fbbf24}.card-heading{font-size:11px;color:#cbd5e1;font-weight:800;letter-spacing:.06em}.card-value{font-size:27px;font-weight:800;margin:5px 0}.card-meta{font-size:12px;color:#b7c6d8}.signal-up{color:#22c55e}.signal-down{color:#ef4444}.signal-neutral{color:#fbbf24}
.st-key-coin_chart_panel,.st-key-coin_market_panel{background:linear-gradient(110deg,#17263c,#121e30);border:1px solid #334b66;border-radius:14px;padding:12px;height:360px;box-sizing:border-box}
</style>''')
st.html('<div class="masthead"><div class="kicker">BTC AND THINGS · COINBASE RESEARCH</div><div class="title">Coinbase Market Tracker</div><div class="sub">coin.shaneathon.com · BTC · ETH · XRP · SOL · independent from PBot and CBot wallets</div></div>')
product=st.radio('Asset',PRODUCTS,horizontal=True,format_func=lambda p:NAMES[p]+' · '+p.split('-')[0])
with st.sidebar:
    st.markdown('### Data controls')
    st.caption('Coinbase Advanced public spot markets. This tracker cannot place orders.')
    auto=st.toggle('Refresh tracker every 10 seconds',value=True)
    if st.button('Refresh market data now'): st.rerun()


def setting(name):
    try: value=st.secrets.get(name,'')
    except Exception: value=''
    return str(value or os.environ.get(name,''))


@st.cache_data(ttl=5,show_spinner=False)
def status(url,token): return fetch(url,token)


def render():
    report={}
    url,token=setting('COIN_STATUS_URL'),setting('COIN_READ_TOKEN')
    if not url or not token:
        st.info('SETUP · The Coinbase research collector is not connected yet. No prices, signals or history are invented.')
    else:
        try: report=status(url,token)
        except Exception as exc: st.error('Coinbase tracker feed unavailable ('+type(exc).__name__+').')
    now=time.time()
    state=report.get('products',{}).get(product,{})
    rows=state.get('candles',[])
    book=state.get('book',{})
    metrics=state.get('indicators',{})
    quality=state.get('quality',{})
    last=rows[-1] if rows else {}
    feed_age=now-report.get('observed_at',0) if report else None
    signal_ready=bool(metrics.get('ready') and rows and 0<=now-(rows[-1]['start']+60)<=120 and feed_age is not None and 0<=feed_age<=120)
    book_age=now-book['book_time'] if book else None
    book_fresh=book_age is not None and 0<=book_age<=15
    def price(value):
        if value is None: return 'PENDING'
        return f"${float(value):,.5f}" if product=='XRP-USD' else f"${float(value):,.2f}"
    left,right=st.columns([1,1],gap='medium')
    with left:
        with st.container(key='coin_market_panel'):
            st.markdown('#### '+NAMES[product]+' · Coinbase USD spot')
            a,b=st.columns(2)
            a.metric('Last completed close',price(last.get('close')))
            b.metric('Feed status','FRESH' if book_fresh and signal_ready else 'STALE / PENDING')
            a,b=st.columns(2)
            a.metric('Best bid · observed',price(book.get('bid')))
            b.metric('Best ask · observed',price(book.get('ask')))
            a,b=st.columns(2)
            a.metric('Spread · basis points',f"{book['spread_bps']:.2f}" if book else 'PENDING')
            b.metric('Book age',f'{book_age:.0f}s' if book_age is not None else 'PENDING')
            st.caption('Continuous spot market · no contract expiry or Polymarket price-to-beat target.')
            st.caption('Quotes are sampled observations, not guaranteed fills. Prices update when the collector refreshes.')
    with right:
        with st.container(key='coin_chart_panel'):
            header,selector=st.columns([2,1])
            header.markdown('**'+product+' · completed candles**')
            with selector:
                interval=st.radio('Candle interval',('1m','5m','15m'),horizontal=True,label_visibility='collapsed',key='coin_interval')
            if rows:
                frame=pd.DataFrame(rows)
                frame['time']=pd.to_datetime(frame['start'],unit='s',utc=True)
                for k in ('open','high','low','close','volume'): frame[k]=pd.to_numeric(frame[k],errors='coerce')
                if interval!='1m':
                    minutes=int(interval[:-1])
                    grouped=frame.set_index('time').resample(str(minutes)+'min')
                    chart=grouped.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
                    chart=chart[(grouped['close'].count()==minutes)&(chart.index+pd.Timedelta(minutes=minutes)<=pd.Timestamp.fromtimestamp(now,tz='UTC'))].reset_index()
                else: chart=frame
                if not chart.empty: components.html(candle_svg(chart,product,interval),height=260,scrolling=False)
                else: st.info('Waiting for complete candles at this interval.')
            else: st.info('Completed Coinbase candles will appear after the collector is connected.')
            st.caption('Coinbase-only price history. Chart intervals aggregate candles; they are not expiring markets.')
    if report and not signal_ready: st.warning('Momentum signals are paused until fresh, contiguous completed candles are available.')
    direction=metrics.get('direction') if signal_ready else 'PENDING'
    tone={'BUY':'UP','SELL':'DOWN'}.get(direction,'NEUTRAL') if signal_ready else 'PENDING'
    lean,readiness=st.columns(2)
    with lean:
        st.html(signal_card('CURRENT '+product.split('-')[0]+' MOMENTUM LEAN',tone,
            f"EMA9/21 and 3-minute return · RSI(14): {metrics['rsi14']:.1f}" if signal_ready else 'Requires fresh completed Coinbase candles.'))
    with readiness:
        st.html(signal_card('CBOT DATA READINESS','READY' if signal_ready and book_fresh and state.get('bot_ready') else 'PENDING',
            'Read-only data for the separate CBot. Strategy, risk and trading decisions remain in CBot.'))
    st.caption('Indicators always use completed one-minute candles; changing the chart interval changes only the chart.')
    st.caption('Momentum is a transparent research indicator, not a calibrated forecast probability or trading recommendation.')
    overview,liquidity,prints,history,diagnostics=st.tabs(['Market overview','Liquidity & spread','Recent trades','History & export','Data readiness'])
    with overview:
        a,b,c,d=st.columns(4)
        a.metric('RSI (14)',f"{metrics['rsi14']:.1f}" if signal_ready else 'PENDING')
        b.metric('5m price change',f"{metrics['change_5m']:+.2%}" if signal_ready else 'PENDING')
        c.metric('15m price change',f"{metrics['change_15m']:+.2%}" if signal_ready else 'PENDING')
        d.metric('1m return volatility',f"{metrics['volatility_1m']:.3%}" if signal_ready else 'PENDING')
        st.caption('Volatility is the standard deviation of the latest 20 one-minute log returns, not an annualized risk estimate.')
        if signal_ready:
            a,b=st.columns(2)
            a.metric('ATR (14) · price units',price(metrics['atr14']))
            b.metric('Candle VWAP approximation',price(metrics.get('candle_vwap_approx')))
        st.caption('VWAP uses typical candle price × volume over available recent bars; it is not execution-level exchange VWAP.')
    with liquidity:
        if book:
            a,b,c=st.columns(3)
            a.metric('Sampled bid depth · base',book['bid_depth_base'])
            b.metric('Sampled ask depth · base',book['ask_depth_base'])
            c.metric('Depth imbalance',f"{book['depth_imbalance']:+.1%}")
            bids,asks=st.columns(2)
            bids.dataframe(book['bids'],hide_index=True,width='stretch')
            asks.dataframe(book['asks'],hide_index=True,width='stretch')
        else: st.info('Verified product-specific order-book snapshots are pending.')
        st.caption('Up to 20 levels per side, sampled by REST. This is not the full order book, a continuous L2 reconstruction or a liquidity guarantee.')
    with prints:
        trades=state.get('trades',[])
        if trades: st.dataframe(trades,hide_index=True,width='stretch')
        else: st.info('Recent Coinbase trade prints are pending.')
        st.caption('Latest up to 100 trades per poll. BUY/SELL labels are preserved as reported; no maker/taker aggressor interpretation is assumed. Busy-period ticks can be missed.')
    with history:
        if rows:
            st.dataframe(rows[-20:],hide_index=True,width='stretch')
            st.download_button('Export observed completed candles CSV',pd.DataFrame(rows).to_csv(index=False),file_name=product.lower()+'_coinbase_candles.csv',mime='text/csv')
        else: st.info('The independent collector will persist candle, book, trade and product history after deployment.')
        st.caption('This download covers the recent response window. The separate server archive retains observations; the app itself does not run a 24/7 collector.')
    with diagnostics:
        st.json({'product_id':product,'components':state.get('components',{}),'quality':quality,'errors':state.get('errors',{}),'request_latency_ms':state.get('latency_ms',{}),
                 'snapshot_age_seconds':feed_age,'bot_ready_at_collection':state.get('bot_ready',False)})
        st.caption('Account balances, actual fills, fee tiers, news, derivatives/funding and on-chain data are not connected. No authenticated account endpoints are called.')
    st.caption('Research tracker only · no order submission · no wallet access · independent from btc.shaneathon.com, pbot.shaneathon.com and cbot.shaneathon.com')


if auto: st.fragment(run_every='10s')(render)()
else: render()
