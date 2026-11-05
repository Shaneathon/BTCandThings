import json, math, time, sqlite3, os, html
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components  # Main live countdown only

st.set_page_config(page_title="BTC and Things · Trading", page_icon="₿", layout='wide')
st.html("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { color-scheme: dark; }
.stApp {background: #0b1120 !important; color: #e2e8f0 !important;}
html, body, .stApp, .stApp button, .stApp input, .stApp label, .stApp p {font-family: 'Inter',system-ui,sans-serif !important;}
.block-container {max-width: 1600px !important; padding: 1rem 1.5rem 3rem !important;}
h1,h2,h3 {color: #f8fafc !important; font-family:'Inter',sans-serif !important; letter-spacing:-.025em !important; text-transform:none !important;}
h1 {font-size:1.55rem !important;} h2 {font-size:1.2rem !important;} h3 {font-size:1rem !important;}
[data-testid='stMetric'],[data-testid='stExpander'],[data-testid='stDataFrame'] {background:#151f32 !important;border:1px solid #29384e !important;border-radius:12px !important;box-shadow:none !important;}
[data-testid='stMetric'] {padding:12px 15px !important;}
[data-testid='stMetricLabel'] {color:#94a3b8 !important; font-size:.78rem !important;}
[data-testid='stMetricValue'] {color:#f8fafc !important;font-weight:700 !important;font-size:1.4rem !important;overflow-wrap:anywhere;}
[data-testid='stAlert'] {border-radius:10px !important;}
.stButton button,.stDownloadButton button {background:#1e3a5f !important;color:#e0f2fe !important;border:1px solid #36577b !important;border-radius:9px !important;box-shadow:none !important;}
.stButton button:hover,.stDownloadButton button:hover {background:#264e7d !important;}
[data-testid='stTabs'] button {font-weight:600 !important;}
.signal-hero {background:linear-gradient(120deg,#172b42,#111c2d);border:1px solid #34465e;padding:15px 18px;border-radius:12px;margin:8px 0;}
.signal-label {color:#93c5fd;font-size:11px;letter-spacing:1px;font-weight:700;}
.signal-title {font-size:23px;font-weight:800;color:#fbbf24;line-height:1.5;}
.signal-sub {color:#a9b9cc;font-size:13px;}
.retro-section {font-family:'Inter',sans-serif;letter-spacing:0;color:#e2e8f0;border-bottom:1px solid #29384e;padding:10px 0;margin:14px 0;font-weight:700;}
/* Trading terminal: shared visual language for signal cards */
.signal-card {min-height:174px; background:linear-gradient(125deg,#13243b,#0d192a);border:1px solid #334b66;border-radius:15px;padding:18px 22px;margin:3px 0 10px;box-sizing:border-box;}
.signal-card.up {border-color:#22c55e;box-shadow:inset 0 0 0 1px #22c55e33;}
.signal-card.down {border-color:#ef4444;box-shadow:inset 0 0 0 1px #ef444433;}
.signal-card.neutral {border-color:#fbbf24;box-shadow:inset 0 0 0 1px #fbbf2433;}
.signal-card .card-heading {font-size:13px;color:#cbd5e1;letter-spacing:.07em;font-weight:800;}
.signal-card .card-value {font-size:42px;font-weight:800;letter-spacing:-.045em;line-height:1.2;margin:10px 0 6px;}
.signal-card .card-meta {font-size:13px;color:#b7c6d8;line-height:1.6;}
.signal-up {color:#22c55e!important;}.signal-down {color:#ef4444!important;}.signal-neutral {color:#fbbf24!important;}
.preflight-advice {background:#14243a;border:1px solid #344b66;border-radius:12px;padding:13px 17px;margin:6px 0 15px;font-size:14px;color:#e2e8f0;}
.preflight-advice strong {color:#fbbf24;}
.modern-masthead {background:linear-gradient(105deg,#13263e,#0f192b);border:1px solid #2a405b;border-radius:16px;padding:18px 22px;margin-bottom:14px;}
.modern-kicker {font-size:11px;letter-spacing:1.6px;color:#38bdf8;font-weight:700;}
.modern-title {font-size:clamp(22px,2.5vw,32px);font-weight:800;letter-spacing:-.04em;color:#f8fafc;margin-top:3px;}
.modern-sub {color:#94a3b8;font-size:12px;margin-top:4px;}
@media(max-width:700px){.block-container{padding:.65rem .65rem 2rem !important;}.modern-masthead{padding:13px 14px;}}

/* Compact dashboard layout */
.block-container {
    max-width: 1700px !important;
    padding: .5rem 1rem 1.5rem !important;
}
[data-testid="stVerticalBlock"] {
    gap: .35rem !important;
}
[data-testid="stHorizontalBlock"] {
    gap: .65rem !important;
    align-items: stretch !important;
}
.signal-card {
    min-height: 105px !important;
    padding: 10px 14px !important;
    margin: 2px 0 5px !important;
    border-radius: 9px !important;
}
.signal-card .card-heading {
    font-size: 11px !important;
}
.signal-card .card-value {
    font-size: 25px !important;
    margin: 5px 0 3px !important;
    line-height: 1.15 !important;
}
.signal-card .card-meta {
    font-size: 11px !important;
    line-height: 1.35 !important;
}
[data-testid="stMetric"] {
    padding: 7px 10px !important;
    border-radius: 8px !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.15rem !important;
}
.modern-masthead {
    padding: 10px 14px !important;
    margin-bottom: 7px !important;
    border-radius: 10px !important;
}
.modern-title {
    font-size: 22px !important;
}
.retro-section {
    padding: 5px 0 !important;
    margin: 7px 0 !important;
}
@media(max-width:700px) {
    .signal-card {
        min-height: 95px !important;
    }
    .signal-card .card-value {
        font-size: 21px !important;
    }
}
</style>""")
st.html("""<div class="modern-masthead"><div class="modern-kicker">BTC AND THINGS · TRADING INTELLIGENCE · POLYMARKET US</div><div class="modern-title">Bitcoin Trade Tracker</div><div class="modern-sub">15-minute markets · live countdown · automatic 60-second market refresh</div></div>""")
# The live countdown uses its own JavaScript clock and does not need a rerun.
# Auto-refresh is opt-in to avoid a third-party component loading failure and
# repeated full-page redraws. Historical recording still occurs on app reruns.
with st.sidebar:
    st.caption("Dashboard updates")
    auto_refresh_enabled = st.toggle("Automatic market refresh", value=True,
        help="Enable to refresh market data every 60 seconds. The countdown stays live even when disabled.")
    if st.button("Refresh market data now", key="manual_market_refresh"):
        st.rerun()
    if not auto_refresh_enabled:
        st.caption("Live countdown continues; price, chart and signals update on manual refresh.")
if auto_refresh_enabled:
    # Native Streamlit fragment: no third-party JavaScript component required.
    # The fragment is invoked once on each full run and re-executes after 60 seconds.
    st.session_state['_btc_last_full_run'] = time.monotonic()

    @st.fragment(run_every="60s")
    def _native_market_refresh():
        if time.monotonic() - st.session_state.get('_btc_last_full_run', time.monotonic()) >= 55:
            st.rerun(scope="app")

    _native_market_refresh()
    st.sidebar.caption("Automatic market refresh: ON · every 60 seconds")

@st.cache_data(ttl=15)
def get_json(url, params=None):
    r=requests.get(url,params=params,timeout=(3, 5),headers={'User-Agent':'BTCSignalLab/0.1'})
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=30)
def candles():
    raw=get_json('https://api.kraken.com/0/public/OHLC',{'pair':'XBTUSD','interval':1})
    if raw.get('error'): raise ValueError(str(raw['error']))
    key=next(k for k in raw['result'] if k!='last')
    rows=raw['result'][key]
    df=pd.DataFrame(rows,columns=['time','open','high','low','close','vwap','volume','count'])
    for c in ['open','high','low','close','vwap','volume']:df[c]=pd.to_numeric(df[c])
    df['time']=pd.to_datetime(df['time'],unit='s',utc=True)
    return df.iloc[:-1].copy() # discard potentially incomplete last minute

def rsi(close, n=14):
    d=close.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); down=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+up/down.replace(0,np.nan))

def normal_cdf(x): return 0.5*(1+math.erf(x/math.sqrt(2)))

def parse_array(v):
    if isinstance(v,list): return v
    try: return json.loads(v)
    except Exception:return []

now=int(time.time()); start=now//900*900; remaining=max(0,start+900-now)
slug=f'btc-updown-15m-{datetime.fromtimestamp(start,timezone.utc):%Y-%m-%d-%H%M}z'
# Browser-side UTC-aligned countdown. Runs continuously without refreshing Streamlit.
# Polymarket BTC 15m market slugs follow UTC epoch 900-second boundaries.
top_left, top_right = st.columns([1, 1], gap="medium")
with top_left:
    timer_top_slot=st.empty()
with top_right:
    chart_top_slot=st.empty()
# Live countdown is shown in the left panel; candle chart is on the right.
# Reserve top-of-dashboard positions; fill after market and indicator data loads.
lean_col, preflight_col = st.columns([1, 1], gap="medium")
with lean_col:
    lean_top_slot=st.empty()
with preflight_col:
    preflight_top_slot=st.empty()
ending_top_slot=st.empty()
US_GATEWAY='https://gateway.polymarket.us'
@st.cache_data(ttl=15)
def us_get(path):
    return get_json(US_GATEWAY+path)
# US market discovery: the event URL slug is not necessarily an API market slug.
# Use public event/market listings and require an exact slug match; never guess a contract.
@st.cache_data(ttl=120, show_spinner=False)
def us_discover(event_slug):
    """Discover a US event/contract conservatively; never infer outcomes by order."""
    diagnostics=[]
    found_event=None
    found_market=None

    # The documented SDK exposes event-by-slug. Probe this before broad listings.
    for path in ('/v1/events/slug/'+event_slug, '/v1/event/slug/'+event_slug):
        try:
            response=us_get(path)
            obj=response.get('data',response) if isinstance(response,dict) else response
            if isinstance(obj,dict) and isinstance(obj.get('event'),dict):
                obj=obj['event']
            if isinstance(obj,dict) and obj.get('slug')==event_slug:
                found_event=obj
                diagnostics.append('Direct event slug: matched '+path)
                break
            diagnostics.append('Direct event slug: response did not confirm exact slug ('+path+')')
        except requests.HTTPError as exc:
            diagnostics.append('Direct event slug '+path+': HTTP '+str(exc.response.status_code if exc.response is not None else 'error'))
        except Exception as exc:
            diagnostics.append('Direct event slug '+path+': '+str(exc)[:120])

    # A direct event match is sufficient; do not scan 4,000 unrelated records
    # on every 20-second refresh. Listings are only a fallback.
    if not found_event:
        for kind in ('events','markets'):
            total=0
            for offset in range(0,200,200):
                try:
                    data=get_json(US_GATEWAY+'/v1/'+kind,{'limit':200,'offset':offset})
                    root=data.get('data',data) if isinstance(data,dict) else data
                    items=root.get(kind,root.get('items',root.get('results',[]))) if isinstance(root,dict) else root
                    if not isinstance(items,list): break
                    total+=len(items)
                    matches=[x for x in items if isinstance(x,dict) and x.get('slug')==event_slug]
                    if len(matches)==1:
                        if kind=='events': found_event=matches[0]
                        else: found_market=matches[0]
                    if found_event or found_market or len(items)<200: break
                except Exception as exc:
                    diagnostics.append(f'{kind} listing error: {str(exc)[:120]}')
                    break
            diagnostics.append(f'{kind}: inspected {total} records (fallback only)')

    # Only use a linked market when there is precisely one candidate and its
    # parent is an exact match. Multiple contracts need manual outcome review.
    if found_event and not found_market:
        linked=found_event.get('markets',[])
        if isinstance(linked,dict): linked=list(linked.values())
        if isinstance(linked,list) and len(linked)==1 and isinstance(linked[0],dict):
            found_market=linked[0]
            diagnostics.append('Found one market linked to the exact event; outcome mapping still unverified')
        elif isinstance(linked,list):
            diagnostics.append(f'Exact event contains {len(linked)} linked market(s)')
    if not found_event and not found_market:
        diagnostics.append('No exact US API match found. Website URL alone does not establish an API instrument ID.')
    return found_event,found_market,diagnostics

us_event,market,us_diagnostics=us_discover(slug)
if not us_event and not market:
    st.warning('US event/market not verified for this exact 15-minute window. Live US odds unavailable; no substitute market will be used.')
if not market:
    st.caption('US contract mapping not verified; ticket prices remain pending.')
with st.expander('US API connection diagnostics',expanded=False):
    st.code('\n'.join(us_diagnostics))
    st.caption('Exact event slug lookup is attempted first. Listings are a fallback only. No odds are inferred without verified contract mapping.')
try: df=candles()
except Exception as exc:
    st.error(f'BTC candle feed unavailable: {exc}. Cannot calculate indicators.');st.stop()
if len(df)<50:st.error('Not enough complete candles');st.stop()
last=df.iloc[-1]; price=float(last['close']); df['ema9']=df.close.ewm(span=9,adjust=False).mean();df['ema21']=df.close.ewm(span=21,adjust=False).mean();df['rsi14']=rsi(df.close)
returns=np.log(df.close).diff().dropna(); minute_vol=float(returns.tail(120).std()); rv=minute_vol*math.sqrt(max(remaining/60,0.25)); ema9=float(df.ema9.iloc[-1]);ema21=float(df.ema21.iloc[-1]);rs=float(df.rsi14.iloc[-1]);
vol20=float(df.volume.tail(20).mean());vol5=float(df.volume.tail(5).mean());
# Only an explicit reference in the CURRENT US event can be displayed as API-sourced.
def extract_us_reference(obj):
    queue=[obj]
    while queue:
        item=queue.pop()
        if isinstance(item,list): queue.extend(item)
        elif isinstance(item,dict):
            for key in ('priceToBeat','price_to_beat'):
                try:
                    value=float(item.get(key))
                    if math.isfinite(value) and value>0: return value
                except (TypeError,ValueError): pass
            for key in ('data','event','eventMetadata','metadata'):
                if key in item: queue.append(item[key])
    return None

# Pixel V8: fetch the full US Retail market record. The embedded market in an
# event can be stale/incomplete; the documented endpoint exposes assetPriceTerms.
# Source: https://docs.polymarket.us/api-reference/markets/get-market-by-slug
@st.cache_data(ttl=12, show_spinner=False)
def us_full_market(contract_slug):
    response=us_get('/v1/market/slug/'+contract_slug)
    root=response.get('data',response) if isinstance(response,dict) else response
    if isinstance(root,dict) and isinstance(root.get('market'),dict):
        root=root['market']
    if not isinstance(root,dict) or root.get('slug')!=contract_slug:
        raise ValueError('Full US market response did not match the requested contract slug')
    return root

full_market=None
full_market_error=None
if market:
    contract_slug=market.get('slug') or market.get('symbol')
    if contract_slug:
        try:
            full_market=us_full_market(str(contract_slug))
        except Exception as exc:
            full_market_error=str(exc)

# Only use the explicitly documented typed priceToBeat, not arbitrary numbers.
def typed_us_price_to_beat(obj):
    if not isinstance(obj,dict): return None
    terms=obj.get('assetPriceTerms')
    if not isinstance(terms,dict): return None
    asset=terms.get('asset') or {}
    if not isinstance(asset,dict) or str(asset.get('symbol','')).lower() not in ('btc','xbt'):
        return None
    market_type=str(terms.get('marketType','')).upper()
    if 'UPDOWN' not in market_type and 'UP_DOWN' not in market_type:
        return None
    raw=terms.get('priceToBeat')
    if not isinstance(raw,dict) or str(raw.get('currency','USD')).upper()!='USD':
        return None
    try:
        value=float(raw.get('value'))
        return value if math.isfinite(value) and value>0 else None
    except (TypeError,ValueError): return None

# Pixel V8: inspect reference metadata from the exact US event and linked market.
# This is intentionally read-only: an arbitrary field containing "price" is not
# evidence of an official BRTI settlement reference.
def us_reference_field_report(*sources):
    rows=[]
    seen=set()
    def walk(obj, path, depth=0):
        if depth>7 or len(rows)>=100: return
        if isinstance(obj,dict):
            for k,v in obj.items():
                location=f'{path}.{k}'
                if isinstance(v,(dict,list)):
                    walk(v,location,depth+1)
                elif any(term in str(k).lower() for term in ('strike','reference','beat','brti','settlement','oracle','indexprice')):
                    if location not in seen:
                        rows.append({'API field':location,'Value':str(v)[:160]})
                        seen.add(location)
        elif isinstance(obj,list):
            for i,v in enumerate(obj[:8]): walk(v,f'{path}[{i}]',depth+1)
    for label,source in sources:
        if source is not None: walk(source,label)
    return rows

with st.expander('US price-to-beat investigation · event and contract metadata', expanded=False):
    st.caption('The full US market record is cached briefly between dashboard refreshes. A candidate field is NOT automatically treated as the official BRTI value.')
    ref_rows=us_reference_field_report(('US event',us_event),('US linked market',market),('US full market',full_market))
    if ref_rows:
        st.dataframe(pd.DataFrame(ref_rows),hide_index=True,width="stretch")
    else:
        st.info('No reference, strike, BRTI, or price-to-beat fields found in the current event/contract metadata.')
    if full_market_error: st.warning('Full market lookup: '+full_market_error)
    if full_market is not None:
        st.caption('Full US market assetPriceTerms (documented API):')
        st.json(full_market.get('assetPriceTerms'))
    st.markdown(f'[Check the matching Polymarket US event](https://polymarket.us/event/{slug})')
    st.caption('If the website shows a Price to Beat but the API omits it, copy the value into the manual field below. This does not verify it through the API.')

# Reference provenance matters: Gamma values are market-supplied; Kraken is NOT.
# An automatic spot proxy keeps exploratory charts usable without claiming verification.
strike=0.0
reference=None
reference_source='Unavailable'
try:
    reference=typed_us_price_to_beat(full_market)
    if reference is None: reference=typed_us_price_to_beat(market)
except Exception as exc: st.caption(f'US reference lookup failed: {exc}')
if reference is not None:
    strike=reference
    reference_source='Polymarket US Retail API assetPriceTerms.priceToBeat'
    st.info(f'US event/contract reports price to beat: ${strike:,.2f} · {slug}')
else:
    st.warning('US price to beat not yet published in the full US market record. It normally appears shortly after the window starts. Kraken is NOT the US BRTI settlement reference.')
    st.caption('US-only data. International Gamma and previous-market fallback disabled.')
    with st.expander('Reference options · official value or research-only proxy',expanded=True):
        manual=st.number_input('Price to beat copied from the matching Polymarket market (optional)',min_value=0.0,value=0.0,step=1.0,format='%.2f',key=f'manual_{slug}')
        use_proxy=st.checkbox('Use automatic Kraken opening-price proxy for RESEARCH ONLY (not official)',value=False,key='proxy_opt_in')
        if manual>0:
            strike=manual
            reference_source='Manually entered (not API-verified)'
        elif use_proxy:
            # Kraken OHLC timestamps are minute starts. Use the last completed
            # 1-minute close ending at or before the market boundary.
            eligible=df[df['time'].astype('int64')//10**9 + 60 <= start]
            if not eligible.empty:
                proxy_row=eligible.iloc[-1]
                proxy_age=start-(int(proxy_row['time'].timestamp())+60)
                if proxy_age<=120:
                    strike=float(proxy_row['close'])
                    reference_source=f'Kraken spot proxy (unverified; {proxy_age}s old at opening)'
                else:
                    st.warning('No sufficiently recent opening candle for a proxy.')
            else:
                st.warning('Opening candle unavailable in the current Kraken history.')
        if strike>0:
            st.info(f'Using ${strike:,.2f} · {reference_source}. Do not treat this as an official settlement value.')
verified_reference=reference is not None  # Typed US Retail API field; official settlement result still separate

# Lightweight, server-rendered SVG candlesticks avoid Plotly's dynamically loaded frontend module.
# Kraken candles are NOT the official Polymarket US BRTI settlement reference.
with chart_top_slot.container():
    chart_header, chart_interval_col = st.columns([2, 1], vertical_alignment="center")
    with chart_header:
        st.markdown("**BTC / USD · Kraken candles**")
    with chart_interval_col:
        chart_interval = st.radio("Candle interval", ["1m", "5m"], horizontal=True,
                                  label_visibility="collapsed", key="modern_candle_interval")
    candle_frame = df.set_index('time')[['open', 'high', 'low', 'close']].copy()
    if chart_interval == '5m':
        candle_frame = candle_frame.resample('5min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        candle_frame = candle_frame[candle_frame.index < pd.Timestamp.now(tz='UTC').floor('5min')]
    candle_frame = candle_frame.tail(80)
    if candle_frame.empty:
        st.warning('No completed candles available for this interval.')
    else:
        # CSS/HTML candlesticks: st.html reliably renders these ordinary HTML
        # elements (the dashboard cards use the same rendering mechanism).
        # Avoid raw <svg>, which can be stripped by HTML sanitization, and
        # avoid external JS chart components and Streamlit media endpoints.
        chart_high = float(candle_frame['high'].max())
        chart_low = float(candle_frame['low'].min())
        if reference is not None and chart_low * 0.98 <= reference <= chart_high * 1.02:
            chart_high = max(chart_high, float(reference))
            chart_low = min(chart_low, float(reference))
        chart_pad = max((chart_high - chart_low) * 0.06, 0.5)
        chart_high += chart_pad
        chart_low -= chart_pad
        chart_span = max(chart_high - chart_low, 1e-9)
        def chart_y(v):
            return (chart_high - float(v)) / chart_span * 100.0
        chart_parts = ["""<style>
        .btc-chart{position:relative;height:300px;background:#151f32;border:1px solid #29384e;
            border-radius:12px;overflow:hidden;margin:4px 0 8px}
        .btc-plot{position:absolute;left:8px;right:84px;top:12px;bottom:28px}
        .btc-grid{position:absolute;left:0;right:0;border-top:1px solid #29384e;height:0}
        .btc-axis{position:absolute;right:-78px;transform:translateY(-50%);font:12px system-ui;
            color:#94a3b8;white-space:nowrap}
        .btc-candle{position:absolute;top:0;bottom:0}
        .btc-wick{position:absolute;width:2px;transform:translateX(-50%);border-radius:1px}
        .btc-body{position:absolute;transform:translateX(-50%);border-radius:1px;min-height:2px}
        .btc-target{position:absolute;left:0;right:0;border-top:2px dashed #fbbf24;height:0}
        .btc-time{position:absolute;bottom:8px;color:#94a3b8;font:12px system-ui}
        </style><div class="btc-chart" role="img" aria-label="Kraken BTC USD candlestick chart"><div class="btc-plot">"""]
        for tick in range(5):
            val = chart_low + chart_span * tick / 4
            y = chart_y(val)
            chart_parts.append(f'<div class="btc-grid" style="top:{y:.3f}%"><span class="btc-axis">${val:,.0f}</span></div>')
        count = len(candle_frame)
        candle_width = min(68.0 / count, 2.5)
        for i, row in enumerate(candle_frame.itertuples()):
            x = (i + 0.5) * 100 / count
            wick_top, wick_bottom = chart_y(row.high), chart_y(row.low)
            open_y, close_y = chart_y(row.open), chart_y(row.close)
            body_top, body_bottom = min(open_y, close_y), max(open_y, close_y)
            color = '#22c55e' if row.close >= row.open else '#f87171'
            chart_parts.append(
                f'<div class="btc-candle" style="left:{x:.4f}%">'
                f'<div class="btc-wick" style="top:{wick_top:.3f}%;height:{max(wick_bottom-wick_top,.12):.3f}%;background:{color}"></div>'
                f'<div class="btc-body" style="top:{body_top:.3f}%;height:{max(body_bottom-body_top,.35):.3f}%;width:clamp(2px,{candle_width:.4f}vw,9px);background:{color}"></div>'
                '</div>')
        if reference is not None and chart_low <= reference <= chart_high:
            chart_parts.append(f'<div class="btc-target" style="top:{chart_y(reference):.3f}%"></div>')
        chart_parts.append('</div>')
        chart_parts.append(f'<span class="btc-time" style="left:12px">{candle_frame.index[0]:%H:%M} UTC</span>')
        chart_parts.append(f'<span class="btc-time" style="right:90px">{candle_frame.index[-1]:%H:%M} UTC</span>')
        chart_parts.append('</div>')
        st.html(''.join(chart_parts))
        st.caption('Completed Kraken candles · green = up, red = down · yellow dashed line = US target when available. Not BRTI settlement prices.')

# Shared persistent history database for the top-of-page predictor.
ARCHIVE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')

# Pixel V11.1: initialize archive BEFORE the predictor reads from it.
# CREATE TABLE IF NOT EXISTS never deletes existing history. The archive section
# below can continue writing to these same tables.
def initialize_us_history(db_path):
    with sqlite3.connect(db_path, timeout=10) as db:
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS us_market_samples (
            event_slug TEXT NOT NULL, captured INTEGER NOT NULL, market_slug TEXT,
            window_start INTEGER, window_end INTEGER, seconds_left INTEGER,
            us_price_to_beat REAL, kraken_spot REAL, model_up REAL,
            up_long_quote REAL, down_short_quote REAL, best_bid REAL, best_ask REAL,
            quote_status TEXT, PRIMARY KEY(event_slug,captured))""")
        db.execute("""CREATE TABLE IF NOT EXISTS us_market_results (
            event_slug TEXT PRIMARY KEY, market_slug TEXT, window_end INTEGER,
            official_winner TEXT, verified_at INTEGER, source TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING')""")
        # Add missing columns on older installations without dropping records.
        required = {
            'us_market_samples': {
                'market_slug':'TEXT', 'window_start':'INTEGER', 'window_end':'INTEGER',
                'seconds_left':'INTEGER', 'us_price_to_beat':'REAL', 'kraken_spot':'REAL',
                'model_up':'REAL', 'up_long_quote':'REAL', 'down_short_quote':'REAL',
                'best_bid':'REAL', 'best_ask':'REAL', 'quote_status':'TEXT'},
            'us_market_results': {
                'market_slug':'TEXT', 'window_end':'INTEGER', 'official_winner':'TEXT',
                'verified_at':'INTEGER', 'source':'TEXT',
                'status':"TEXT NOT NULL DEFAULT 'PENDING'"}}
        for table, columns in required.items():
            existing = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            for name, sql_type in columns.items():
                if name not in existing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}')
        db.execute('CREATE INDEX IF NOT EXISTS us_samples_by_time ON us_market_samples(captured)')
        db.commit()

history_ready = False
try:
    initialize_us_history(ARCHIVE)
    history_ready = True
except (sqlite3.Error, OSError) as exc:
    st.warning(f'Historical database is temporarily unavailable ({type(exc).__name__}). Baseline forecast will continue without calibration.')

# PIXEL V12 — Supabase persistence (server-side only).
# Uses Streamlit secrets; never place credentials in GitHub or in browser HTML.
def cloud_settings():
    try:
        url=str(st.secrets.get("SUPABASE_URL","")).strip().rstrip("/")
        key=str(st.secrets.get("SUPABASE_KEY","")).strip()
        if url.startswith("https://") and key:
            return url,key
    except Exception:
        pass
    return None,None

CLOUD_URL,CLOUD_KEY=cloud_settings()
CLOUD_READY=bool(CLOUD_URL and CLOUD_KEY)
CLOUD_ERROR=None

def cloud_request(method,table,params=None,payload=None,prefer=None):
    if not CLOUD_READY:
        raise RuntimeError("Supabase secrets are missing")
    headers={"apikey":CLOUD_KEY,
             "Content-Type":"application/json","Accept":"application/json"}
    # New Supabase sb_secret_ keys are API keys, not JWT bearer tokens.
    if not CLOUD_KEY.startswith("sb_secret_"):
        headers["Authorization"]="Bearer "+CLOUD_KEY
    if prefer: headers["Prefer"]=prefer
    response=requests.request(method,CLOUD_URL+"/rest/v1/"+table,
        headers=headers,params=params,json=payload,timeout=(3, 5))
    if not response.ok:
        raise RuntimeError("Supabase HTTP "+str(response.status_code)+
                           ": "+response.text[:180])
    if not response.content: return []
    return response.json()

def utc_iso(epoch):
    return datetime.fromtimestamp(int(epoch),timezone.utc).isoformat()

@st.cache_data(ttl=90,show_spinner=False)
def cloud_calibration_history():
    """Only one early observation per VERIFIED market is used for calibration."""
    if not CLOUD_READY: return pd.DataFrame()
    results=cloud_request("GET","btc_markets",params={
        "select":"market_slug,official_winner",
        "settlement_status":"eq.VERIFIED",
        "official_winner":"in.(UP,DOWN)","limit":"1000"})
    if not results: return pd.DataFrame()
    winners={r["market_slug"]:r["official_winner"] for r in results}
    # Paginate samples, instead of silently assuming a single default 1,000-row page.
    samples=[]
    for offset in range(0,20000,1000):
        batch=cloud_request("GET","btc_predictions",params={
            "select":"market_slug,recorded_at,seconds_remaining,predicted_up_probability",
            "market_slug":"in.("+",".join('"'+k.replace('"','')+'"' for k in winners)+")",
            "predicted_up_probability":"not.is.null",
            "order":"recorded_at.asc","offset":str(offset),"limit":"1000"})
        samples.extend(batch)
        if len(batch)<1000:break
    if not samples:return pd.DataFrame()
    frame=pd.DataFrame(samples)
    frame["event_slug"]=frame["market_slug"]
    frame["model_up"]=pd.to_numeric(frame["predicted_up_probability"],errors="coerce")
    frame["seconds_left"]=pd.to_numeric(frame["seconds_remaining"],errors="coerce")
    frame["official_winner"]=frame["market_slug"].map(winners)
    frame["captured"]=pd.to_datetime(frame["recorded_at"],utc=True,errors="coerce")
    return frame[["event_slug","model_up","seconds_left","official_winner","captured"]]

# Put the official US price-to-beat in the middle of the timer panel.
# Show an explicit non-official label for manually supplied or proxy values.
if reference is not None:
    beat_display=f'${reference:,.2f}'
    beat_source='OFFICIAL US MARKET'
elif strike>0:
    beat_display=f'${strike:,.2f}'
    beat_source='MANUAL / RESEARCH PROXY · NOT VERIFIED'
else:
    beat_display='PENDING'
    beat_source='OFFICIAL REFERENCE NOT AVAILABLE'
with timer_top_slot:
    components.html("""
    <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
    *{box-sizing:border-box}body{margin:0;background:transparent;color:#edf4ff;font-family:system-ui,-apple-system,sans-serif}
    .panel{background:linear-gradient(110deg,#17263c,#121e30);border:1px solid #334b66;border-radius:14px;padding:22px 22px;min-height:348px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:none}
    .top{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}.label{font-size:11px;letter-spacing:1.7px;color:#9dafc8;font-weight:700}
    .time{color:#f8fafc;font-size:clamp(38px,5vw,65px);font-variant-numeric:tabular-nums;font-weight:800;letter-spacing:1px}.beat{text-align:left;min-width:160px}.beat-value{font-size:25px;font-weight:800;color:#38bdf8;font-variant-numeric:tabular-nums}.beat-source{font-size:10px;color:#9dafc8;margin-top:3px}.stage{font-size:13px;color:#38bdf8;font-weight:700}
    .track{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:20px}.seg{height:5px;border-radius:6px;background:#2c3c52;overflow:hidden}.fill{height:100%;width:0;background:#ffc36a;transition:width .2s linear}
    .meta{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:4px;color:#9dafc8;font-size:12px}
    </style></head><body><div class="panel"><div class="top"><div><div class="label">POLYMARKET · BTC 15-MINUTE WINDOW</div><div id="timer" class="time">--:--</div></div><div class="beat"><div class="label">US PRICE TO BEAT</div><div class="beat-value">___BEAT_DISPLAY___</div><div class="beat-source">___BEAT_SOURCE___</div></div><div><div id="stage" class="stage">Syncing…</div><div id="window" style="font-size:12px;color:#9dafc8;margin-top:6px"></div></div></div>
    <div class="track"><div class="seg"><div class="fill" id="f0"></div></div><div class="seg"><div class="fill" id="f1"></div></div><div class="seg"><div class="fill" id="f2"></div></div><div class="seg"><div class="fill" id="f3"></div></div><div class="seg"><div class="fill" id="f4"></div></div></div><div class="meta"><span id="elapsed"></span><span id="next"></span></div></div>
    <script>
    function tick(){const now=Date.now()/1000, start=Math.floor(now/900)*900, elapsed=now-start, remain=Math.max(0,Math.ceil(start+900-now)), stage=Math.min(4,Math.floor(elapsed/180));
    const pad=n=>String(n).padStart(2,'0');document.getElementById('timer').textContent=pad(Math.floor(remain/60))+':'+pad(remain%60);
    document.getElementById('stage').textContent=['STAGE 1 · 0–3 MIN','STAGE 2 · 3–6 MIN','STAGE 3 · 6–9 MIN','STAGE 4 · 9–12 MIN','STAGE 5 · 12–15 MIN'][stage];
    const utc=s=>new Date(s*1000).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'UTC'});
    document.getElementById('window').textContent=utc(start)+'–'+utc(start+900)+' UTC';
    for(let i=0;i<5;i++)document.getElementById('f'+i).style.width=(Math.max(0,Math.min(1,(elapsed-i*180)/180))*100)+'%';
    document.getElementById('elapsed').textContent='Elapsed: '+Math.floor(elapsed/60)+'m '+Math.floor(elapsed%60)+'s';
    const next=Math.min(900,(stage+1)*180);document.getElementById('next').textContent='Next 3m boundary in '+pad(Math.floor(Math.max(0,next-elapsed)/60))+':'+pad(Math.ceil(Math.max(0,next-elapsed))%60);
    }tick();setInterval(tick,250);
    </script></body></html>
    """.replace("___BEAT_DISPLAY___",beat_display).replace("___BEAT_SOURCE___",beat_source),height=358,scrolling=False)

# Early lean and pre-window directional research, above the main predictor.
early_ema_slope=float(df.ema9.iloc[-1]-df.ema9.iloc[-4])
early_rsi_prev=float(df.rsi14.iloc[-4])
early_ret3=float(df.close.iloc[-1]/df.close.iloc[-4]-1)
early_votes=[
    1 if ema9>ema21 else -1 if ema9<ema21 else 0,
    1 if early_ema_slope>0 else -1 if early_ema_slope<0 else 0,
    1 if early_ret3>0 else -1 if early_ret3<0 else 0,
    1 if rs>50 else -1 if rs<50 else 0,
    1 if rs>early_rsi_prev else -1 if rs<early_rsi_prev else 0,
]
early_score=sum(early_votes)
early_lean='UP' if early_score>=2 else 'DOWN' if early_score<=-2 else 'NEUTRAL'
early_swing=(ema9!=ema21 and early_ret3*(ema9-ema21)<0 and (rs-early_rsi_prev)*(ema9-ema21)<0)
# Color conveys direction, not forecast certainty.
def signal_tone(direction):
    return {'UP':('up','signal-up','↗'), 'DOWN':('down','signal-down','↘')}.get(direction,('neutral','signal-neutral','→'))

with lean_top_slot.container():
    lean_border, lean_text, lean_arrow = signal_tone(early_lean)
    lean_col, position_col = st.columns(2, gap="medium")
    with lean_col:
        st.html(f'''<div class="signal-card {lean_border}">
      <div class="card-heading">↗ &nbsp; CURRENT BTC LEAN</div>
      <div class="card-value {lean_text}">{early_lean} {lean_arrow}</div>
      <div class="card-meta">Directional agreement: <b>{abs(early_score)}/5</b><br>
      Swing watch: <b>{'WATCH · potential reversal' if early_swing else 'CLEAR'}</b></div>
    </div>''')
    with position_col:
        st.html('''<div class="signal-card neutral">
          <div class="card-heading">POSITION SUGGESTION · RESEARCH MODE</div>
          <div class="card-value signal-neutral">WAIT / OBSERVE</div>
          <div class="card-meta">No validated trading edge yet.<br>
          Continue monitoring the current BTC lean and market conditions.</div>
        </div>''')
    st.caption('Completed Kraken 1-minute candles · spot momentum, not verified contract odds. Position suggestion is research-only.')

# The next market has a different, as-yet-unknown US price-to-beat.
# Therefore only predict the first three minutes of Kraken spot direction, not next contract payout.
next_start=start+900
seconds_to_next=max(0,next_start-now)
preflight=seconds_to_next<=180
# V13.5 — capture one actual observed lean per completed Kraken minute.
# No backfill or fabricated observations; Streamlit must remain actively running.
research_db=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')
with sqlite3.connect(research_db, timeout=15) as minute_db:
    minute_db.execute("""CREATE TABLE IF NOT EXISTS minute_lean_snapshots (
        candle_start INTEGER PRIMARY KEY,
        recorded_at INTEGER NOT NULL,
        window_start INTEGER NOT NULL,
        seconds_to_next INTEGER NOT NULL,
        next_window_start INTEGER NOT NULL,
        spot_close REAL NOT NULL,
        price_to_beat REAL,
        reference_verified INTEGER NOT NULL,
        distance_to_target REAL,
        lean TEXT NOT NULL,
        agreement INTEGER NOT NULL,
        signed_score INTEGER NOT NULL,
        swing_watch INTEGER NOT NULL,
        rsi REAL,
        ema9 REAL,
        ema21 REAL,
        ema9_slope REAL,
        return_3m REAL,
        next_open_spot REAL,
        next_close_3m REAL,
        actual_next_direction TEXT,
        result_status TEXT DEFAULT 'PENDING'
    )""")
    last_candle=int(df.time.iloc[-1].timestamp())
    # Only save if the latest completed candle is recent; avoids pretending a stale
    # API result is a current-minute observation.
    if 0 <= now-(last_candle+60) < 120:
        minute_db.execute("""INSERT OR IGNORE INTO minute_lean_snapshots
        (candle_start,recorded_at,window_start,seconds_to_next,next_window_start,
         spot_close,price_to_beat,reference_verified,distance_to_target,lean,
         agreement,signed_score,swing_watch,rsi,ema9,ema21,ema9_slope,return_3m)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (last_candle,now,start,max(0,start+900-now),start+900,
         float(df.close.iloc[-1]),float(reference) if reference is not None else None,
         int(bool(verified_reference)),
         float(df.close.iloc[-1]-reference) if verified_reference and reference is not None else None,
         early_lean,abs(early_score),early_score,int(early_swing),float(rs),
         float(ema9),float(ema21),early_ema_slope,early_ret3))
    # Compare each saved minute's lean with the NEXT window's first 3m spot move.
    # A candle timestamp is its opening; the close at a boundary comes from
    # the candle starting 60 seconds before that boundary.
    candle_close_map={int(t.timestamp()):float(c) for t,c in zip(df.time,df.close)}
    pending_minute=minute_db.execute("""SELECT candle_start,next_window_start FROM
      minute_lean_snapshots WHERE result_status='PENDING'""").fetchall()
    for candle_start,boundary in pending_minute:
        if now < boundary+180:
            continue
        opening=candle_close_map.get(boundary-60)
        ending=candle_close_map.get(boundary+120)
        if opening is None or ending is None:
            continue  # Leave pending if exact historical candles are unavailable.
        actual='UP' if ending>opening else 'DOWN' if ending<opening else 'FLAT'
        minute_db.execute("""UPDATE minute_lean_snapshots SET next_open_spot=?,
            next_close_3m=?,actual_next_direction=?,result_status='VERIFIED_KRAKEN_PROXY'
            WHERE candle_start=?""",(opening,ending,actual,candle_start))
    minute_db.commit()
    minute_history=pd.read_sql_query("""SELECT * FROM minute_lean_snapshots
        ORDER BY candle_start DESC LIMIT 1500""",minute_db)
with st.expander('Minute-by-minute lean research · V13.5', expanded=False):
    if minute_history.empty:
        st.info('Waiting for the first completed-minute observation.')
    else:
        minute_verified=minute_history[
            minute_history.result_status.eq('VERIFIED_KRAKEN_PROXY') &
            minute_history.actual_next_direction.isin(['UP','DOWN']) &
            minute_history.lean.isin(['UP','DOWN'])]
        a,b,c=st.columns(3)
        a.metric('Saved minute snapshots',len(minute_history))
        b.metric('Evaluated snapshots',len(minute_verified))
        c.metric('Momentum lean accuracy',
            f"{(minute_verified.lean==minute_verified.actual_next_direction).mean():.1%}"
            if len(minute_verified) else 'PENDING')
        if len(minute_verified):
            st.caption(f"Opposite/reversal accuracy: {(minute_verified.lean!=minute_verified.actual_next_direction).mean():.1%}. "
                'Snapshots from one 15-minute window share an outcome and are NOT independent tests.')
        st.caption('Records one snapshot per completed Kraken minute when this dashboard runs. '
            'Outcomes compare the NEXT window opening to 3 minutes later on Kraken, not Polymarket settlement. '
            'No missed minutes are backfilled.')
        view=minute_history.copy()
        view['candle_utc']=pd.to_datetime(view.candle_start,unit='s',utc=True)
        st.dataframe(view[['candle_utc','lean','agreement','signed_score','spot_close',
            'seconds_to_next','actual_next_direction','result_status']].head(100),
            hide_index=True,width="stretch")
        st.download_button('Export minute lean history CSV',minute_history.to_csv(index=False),
            'minute_lean_history.csv','text/csv')

with sqlite3.connect(research_db,timeout=10) as next_db:
    next_db.execute("""CREATE TABLE IF NOT EXISTS next_window_preflight (
      next_start INTEGER PRIMARY KEY, predicted_at INTEGER, spot_at_prediction REAL,
      predicted_direction TEXT, agreement INTEGER, evaluation_end INTEGER,
      opening_spot REAL, spot_after_3m REAL, actual_direction TEXT)""")
    # Non-destructive schema migration. Older records retain their original outcome.
    columns={row[1] for row in next_db.execute('PRAGMA table_info(next_window_preflight)')}
    audit_columns={
        'opening_candle_start':'INTEGER', 'ending_candle_start':'INTEGER',
        'audit_opening_close':'REAL', 'audit_ending_close':'REAL',
        'audit_direction':'TEXT', 'audit_status':'TEXT', 'audit_checked_at':'INTEGER',
        'audit_note':'TEXT', 'signal_version':'TEXT'
    }
    for col,kind in audit_columns.items():
        if col not in columns:
            next_db.execute(f'ALTER TABLE next_window_preflight ADD COLUMN {col} {kind}')
    # A candle timestamp denotes its START. At the window boundary, use the
    # previous completed minute's close; at +3m, use the minute ending there.
    completed_candles={int(t.timestamp()):float(c) for t,c in zip(df.time,df.close)}
    pending=next_db.execute("SELECT next_start,evaluation_end FROM next_window_preflight WHERE actual_direction IS NULL").fetchall()
    for boundary,finish in pending:
        opening=completed_candles.get(boundary-60)
        ending=completed_candles.get(finish-60)
        if now>=finish and opening is not None and ending is not None:
            actual='UP' if ending>opening else 'DOWN' if ending<opening else 'FLAT'
            next_db.execute("UPDATE next_window_preflight SET opening_spot=?,spot_after_3m=?,actual_direction=? WHERE next_start=?",(opening,ending,actual,boundary))
    if preflight and early_lean!='NEUTRAL':
        next_db.execute("""INSERT OR IGNORE INTO next_window_preflight
          (next_start,predicted_at,spot_at_prediction,predicted_direction,agreement,evaluation_end,signal_version)
          VALUES (?,?,?,?,?,?,?)""",(next_start,now,price,early_lean,abs(early_score),next_start+180,'V13.4'))
    # Audit every available record, including older V13.3 rows, without
    # overwriting their originally recorded evaluation. This catches discrepancies.
    records=next_db.execute('SELECT next_start,evaluation_end,predicted_at,opening_spot,spot_after_3m,actual_direction FROM next_window_preflight').fetchall()
    for boundary,finish,predicted_at,old_open,old_end,old_actual in records:
        candle_open=boundary-60
        candle_end=finish-60
        open_close=completed_candles.get(candle_open)
        end_close=completed_candles.get(candle_end)
        if predicted_at is not None and predicted_at>=boundary:
            status,note='INVALID_LATE','Forecast recorded at or after the next window began.'
        elif predicted_at is not None and predicted_at<boundary-180:
            status,note='INVALID_EARLY','Forecast recorded before the defined 3-minute preflight period.'
        elif now<finish:
            status,note='AWAITING_END','Three-minute evaluation period not finished.'
        elif open_close is None or end_close is None:
            status,note='MISSING_CANDLES','Exact completed 1-minute Kraken candles not in current OHLC response.'
        else:
            audited='UP' if end_close>open_close else 'DOWN' if end_close<open_close else 'FLAT'
            mismatch=(old_actual is not None and (old_actual!=audited or (old_open is not None and abs(old_open-open_close)>0.00001) or (old_end is not None and abs(old_end-end_close)>0.00001)))
            status='MISMATCH' if mismatch else 'VERIFIED_PROXY'
            note='Historical recorded evaluation differs from independently recomputed candle values.' if mismatch else 'Exact completed Kraken candle closes matched.'
            next_db.execute("""UPDATE next_window_preflight SET opening_candle_start=?,ending_candle_start=?,
              audit_opening_close=?,audit_ending_close=?,audit_direction=? WHERE next_start=?""",
              (candle_open,candle_end,open_close,end_close,audited,boundary))
        next_db.execute('UPDATE next_window_preflight SET audit_status=?,audit_checked_at=?,audit_note=? WHERE next_start=?',(status,now,note,boundary))
    next_db.commit()
    past=pd.read_sql_query('SELECT * FROM next_window_preflight ORDER BY next_start DESC LIMIT 100',next_db)
with preflight_top_slot.container():
    pre_border, pre_text, pre_arrow = signal_tone(early_lean)
    # Preflight is a distinct research phase; do not claim a new-window trade signal
    # before the final three minutes of the current window.
    pre_direction = early_lean if preflight else 'PENDING'
    pre_border = pre_border if preflight else 'neutral'
    pre_text = pre_text if preflight else 'signal-neutral'
    pre_arrow = pre_arrow if preflight else '◷'
    st.html(f'''<div class="signal-card {pre_border}">
      <div class="card-heading">◎ &nbsp; NEXT WINDOW PREFLIGHT</div>
      <div class="card-value {pre_text}">{pre_direction} {pre_arrow}</div>
      <div class="card-meta">Next 15-minute window in: <b>{seconds_to_next//60:02d}:{seconds_to_next%60:02d}</b><br>
      {'Experimental opening lean · ' + str(abs(early_score)) + '/5 agreement' if preflight else 'Preflight begins with 3 minutes remaining'}</div>
    </div>''')
    st.caption('Next-window first 3 minutes of Kraken spot; not a contract winner forecast.')
    if not preflight:
        suggestion='Preflight has not started. Continue observing the current BTC lean.'
    elif early_lean=='NEUTRAL':
        suggestion='WAIT. No clear opening momentum lean; watch for a stronger directional confirmation.'
    elif early_swing:
        suggestion=f'WATCH {early_lean} CAUTIOUSLY. Reversal risk is flagged; wait for confirmation.'
    else:
        suggestion=f'WATCH {early_lean}. Momentum agreement is {abs(early_score)}/5; wait for confirmation before considering an entry.'
    # Advice appears directly below both cards, across the entire dashboard.
    st.session_state['preflight_suggestion_text']=suggestion
    with st.expander('Next-window preflight history, candle audit and research accuracy'):
        st.markdown('**Candle boundary audit (UTC)**')
        st.caption('Opening reference = close of the 1-minute candle starting 60 seconds BEFORE the new 15-minute boundary. Evaluation = close of the candle starting 2 minutes AFTER the boundary. Both must be completed candles. Original outcomes are retained for comparison.')
        if not past.empty:
            verified=past[(past.audit_status=='VERIFIED_PROXY') & past.audit_direction.isin(['UP','DOWN']) & past.predicted_direction.isin(['UP','DOWN'])]
            mismatch_count=int((past.audit_status=='MISMATCH').sum())
            m1,m2,m3=st.columns(3)
            m1.metric('Audited comparable windows',len(verified))
            m2.metric('Audited opening-direction hit rate',f"{(verified.predicted_direction==verified.audit_direction).mean():.1%}" if len(verified) else 'PENDING')
            m3.metric('Historical evaluation mismatches',mismatch_count)
            if mismatch_count:
                st.warning('Some previously saved evaluations disagree with the candle audit. Those records are excluded from the audited hit rate until investigated.')
            view=past.copy()
            for field in ['next_start','predicted_at','evaluation_end','opening_candle_start','ending_candle_start']:
                view[field+'_utc']=pd.to_datetime(view[field],unit='s',utc=True,errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            fields=['next_start_utc','predicted_at_utc','predicted_direction','agreement',
                    'opening_candle_start_utc','ending_candle_start_utc','audit_opening_close',
                    'audit_ending_close','audit_direction','actual_direction','audit_status','audit_note']
            st.dataframe(view[fields],hide_index=True,width="stretch")
            st.download_button('Export full timestamp and candle audit CSV',view.to_csv(index=False),'next_window_preflight_audit.csv','text/csv')
        else:
            st.caption('No pre-window predictions have been saved yet.')

st.html('<div class="preflight-advice"><strong>◉ PREFLIGHT SUGGESTION</strong> &nbsp; '+
            html.escape(st.session_state.get('preflight_suggestion_text','Observing market momentum.'))+
            '<div style="font-size:11px;color:#94a3b8;margin-top:5px">Research-only Kraken spot guidance; not a verified Polymarket trading edge.</div></div>',
            )

# Pixel V10 — final ABOVE/BELOW target forecast with conservative historical calibration.
# Historical calibration uses ONLY explicitly verified US winners, never Kraken proxies.
with ending_top_slot.container():
    st.markdown('#### Final Target Forecast · Research')
    if not verified_reference or reference is None or reference<=0:
        st.warning('Official US Price to Beat pending. Final-target forecast is paused rather than using an unverified proxy.')
    else:
        # Baseline: zero-drift lognormal model using observed Kraken 1m volatility.
        # This forecasts Kraken spot versus the US reference; it is not a BRTI model.
        final_sigma=max(minute_vol,0.00005)*math.sqrt(max(remaining/60,1))
        final_p=min(.995,max(.005,normal_cdf(math.log(price/reference)/final_sigma)))
        final_gap=price-reference
        stage_bucket=min(4,max(0,(now-start)//180))
        stage_name=f'{stage_bucket*3}–{(stage_bucket+1)*3} minutes elapsed'
        calibrated_p=None
        hist_count=0
        brier=None
        try:
            if CLOUD_READY:
                historical=cloud_calibration_history()
                if not historical.empty:
                    historical=historical[historical.event_slug!=slug]
            else:
                if not history_ready:
                    raise sqlite3.OperationalError('History database not initialized')
                with sqlite3.connect(ARCHIVE,timeout=10) as pred_db:
                    historical=pd.read_sql_query("""
                        SELECT s.event_slug,s.model_up,r.official_winner,
                               s.seconds_left,s.captured
                        FROM us_market_samples s
                        JOIN us_market_results r ON r.event_slug=s.event_slug
                        WHERE r.status='VERIFIED' AND r.official_winner IN ('UP','DOWN')
                          AND s.model_up IS NOT NULL AND s.event_slug != ?
                        ORDER BY s.event_slug,s.captured""",pred_db,params=(slug,))
            if not historical.empty:
                historical['stage']=( (900-historical.seconds_left).clip(lower=0,upper=899)//180 ).astype(int)
                historical=historical[historical.stage==stage_bucket]
                historical=historical.drop_duplicates(subset=['event_slug'],keep='first')
                # Nearby forecasts only: probability within 15 percentage points.
                nearby=historical[(historical.model_up-final_p).abs()<=.15]
                hist_count=len(nearby)
                if hist_count>=30:
                    observed=(nearby.official_winner=='UP').astype(float)
                    # 50 pseudo-observations shrink empirical rates toward the
                    # uncalibrated model until sufficient independent data accrue.
                    calibrated_p=(50*final_p+float(observed.sum()))/(50+hist_count)
                    brier=float(((nearby.model_up-observed)**2).mean())
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError, KeyError, TypeError, RuntimeError, requests.RequestException) as err:
            st.caption(f'Historical calibration temporarily unavailable: {err}. Baseline forecast remains available.')
        final_display=calibrated_p if calibrated_p is not None else final_p
        p1,p2,p3=st.columns(3)
        p1.metric('Forecast: finish ABOVE target',f'{final_display:.1%}')
        p2.metric('Forecast: finish BELOW target',f'{1-final_display:.1%}')
        p3.metric('Kraken spot − official target',f'${final_gap:+,.2f}')
        st.progress(float(final_display),text=f'ABOVE {final_display:.1%}  |  BELOW {1-final_display:.1%}')
        st.caption(f'Current stage: {stage_name} · {remaining//60}m {remaining%60}s remaining · US reference ${reference:,.2f}.')
        if calibrated_p is None:
            st.info(f'**Baseline forecast only.** {hist_count} comparable verified historical markets; at least 30 are required to enable historical adjustment. The tracker is still collecting data.')
        else:
            st.success(f'**Historically adjusted research estimate.** Based on {hist_count} comparable, verified US markets in this elapsed-time stage. Baseline {final_p:.1%}; adjusted {calibrated_p:.1%}.')
            st.caption(f'Historical baseline Brier score in comparable markets: {brier:.3f} (lower is better). This is in-sample, not a prospective validation.')
        st.caption('These percentages model Kraken spot relative to the official US BRTI reference. Because the feeds differ and the model is unvalidated, they are NOT verified probabilities of Polymarket settlement and do not establish a betting edge. Exactly equal settlement is grouped with ABOVE (LONG) under the US contract rule.')
        st.caption('Predictions are archived on each active dashboard refresh. Cloud calibration uses verified US results only; the app must receive refreshes to record observations.')


# Trading-first navigation: legacy research and data operations remain available in Advanced.
trade_tab, performance_tab, advanced_tab = st.tabs(["Trading", "Performance", "Advanced · Research & Diagnostics"])
with trade_tab:
    st.markdown("### Trade opportunity advisor")
    st.warning("WAIT / OBSERVE — a tradable entry/exit model has not yet been validated. The preflight panel above describes experimental Kraken momentum, not a verified buy/sell edge.")
    t1,t2,t3,t4=st.columns(4)
    t1.metric('Kraken BTC spot',f'${price:,.2f}')
    t2.metric('US price to beat',f'${reference:,.2f}' if reference is not None else 'PENDING')
    t3.metric('Spot momentum',early_lean)
    t4.metric('Signal agreement',f'{abs(early_score)}/5')
    st.caption('Momentum is derived from completed Kraken candles. It is not a validated prediction of tradable YES/NO price movement.')
    st.markdown('### Position planning · manual / illustrative')
    pos1,pos2,pos3=st.columns(3)
    with pos1:
        entry_cents=st.number_input('Entry price (¢ per contract)',min_value=1.0,max_value=99.0,value=55.0,step=1.0,key='plan_entry')
    with pos2:
        exit_cents=st.number_input('Target exit price (¢)',min_value=1.0,max_value=99.0,value=75.0,step=1.0,key='plan_exit')
    with pos3:
        shares=st.number_input('Contracts',min_value=1,max_value=100000,value=100,step=1,key='plan_shares')
    gross=(exit_cents-entry_cents)*shares/100
    st.metric('Hypothetical gross P/L if both orders fill',f'${gross:+,.2f}')
    st.caption('Before fees, spread, slippage and execution risk. These inputs do not place orders or track a live position.')
    st.info('Live YES/NO executable quotes, order-flow pressure, and target-hit probability require additional verified data integration. No pressure or profitability signal is fabricated.')
with performance_tab:
    st.markdown('### Model and trading performance')
    st.info('Verified settlement accuracy and executable paper-trade performance will appear here as reliable outcomes and trade quotes become available.')
    st.caption('Detailed historical research, cloud archives, and settlement diagnostics remain accessible in Advanced.')
with advanced_tab:
    # Retro quick-look strip: price is a Kraken spot proxy, NOT US BRTI.
    st.markdown('#### Market Control Panel')
    quick1,quick2,quick3,quick4=st.columns(4)
    quick1.metric('BTC · KRAKEN SPOT',f'${price:,.2f}')
    quick2.metric('US PRICE TO BEAT' if reference is not None else 'MANUAL / KRAKEN PROXY' if strike>0 else 'US PRICE TO BEAT',f'${strike:,.2f}' if strike>0 else 'PENDING')
    quick3.metric('US MARKET ODDS','PENDING' if not market else 'LIVE QUOTES BELOW')
    quick4.metric('SIGNAL','WAIT / OBSERVE')
    st.caption('BTC spot and model calculations are research-only; US BRTI reference and outcome verification are separate.')

    # Two-column workstation: signals/market left, forecasts/history right.
    left_col, right_col = st.columns([1, 1], gap="medium")
    with left_col:
        st.subheader('01 · MARKET RADAR · US TICKET PRICES')
        asks={}; book_ok=False
        st.write('US event:',slug)
        if market:
            market_slug=market.get('slug') or market.get('symbol')
            with st.expander('US contract details · inspect market fields',expanded=False):
                st.json({k:market.get(k) for k in ('id','slug','symbol','question','marketType','outcomes','outcomePrices','active','closed') if k in market})
                st.caption('Official US Crypto FAQs: LONG pays on UP (close >= open); SHORT pays on DOWN. Applies to verified BTC Up/Down contracts.')
            if market_slug:
                # The official US SDK implements its own BBO and book endpoints.
                # Do not guess a REST route from the event URL.
                try:
                    from polymarket_us import PolymarketUS
                except ImportError:
                    st.warning('Official Polymarket US SDK not installed. In Command Prompt run: py -3.12 -m pip install polymarket-us')
                else:
                    try:
                        @st.cache_data(ttl=15,show_spinner=False)
                        def fetch_us_quote_sdk(contract_slug):
                            client=PolymarketUS()
                            try:
                                return client.markets.bbo(contract_slug)
                            finally:
                                client.close()
                        quote=fetch_us_quote_sdk(str(market_slug))
                        st.success('US SDK returned live market quotes for this exact US contract.')
                        # LONG = UP and SHORT = DOWN only when the typed US contract
                        # metadata identifies this as a BTC Up/Down market.
                        md=quote.get('marketData',{}) if isinstance(quote,dict) else {}
                        if not isinstance(md,dict): md={}
                        def quote_value(field):
                            obj=md.get(field)
                            try:
                                val=float(obj.get('value') if isinstance(obj,dict) else obj)
                                return val if math.isfinite(val) and 0<=val<=1 else None
                            except (TypeError,ValueError,AttributeError): return None
                        long_px=quote_value('longQuote')
                        short_px=quote_value('shortQuote')
                        best_ask=quote_value('bestAsk')
                        best_bid=quote_value('bestBid')
                        quote_symbol=md.get('marketSlug')
                        if quote_symbol and str(quote_symbol)!=str(market_slug):
                            st.error('Quote symbol does not match the discovered US contract. Prices suppressed.')
                        elif long_px is not None and short_px is not None:
                            q1,q2,q3,q4=st.columns(4)
                            typed_terms=(full_market or {}).get('assetPriceTerms') or {}
                            typed_asset=typed_terms.get('asset') or {}
                            typed_kind=str(typed_terms.get('marketType','')).upper()
                            mapped=(str(typed_asset.get('symbol','')).lower() in ('btc','xbt') and ('UPDOWN' in typed_kind or 'UP_DOWN' in typed_kind))
                            q1.metric('US UP (LONG)' if mapped else 'US LONG quote',f'{long_px:.0%}')
                            q2.metric('US DOWN (SHORT)' if mapped else 'US SHORT quote',f'{short_px:.0%}')
                            q3.metric('US best ask',f'{best_ask:.0%}' if best_ask is not None else 'n/a')
                            q4.metric('US best bid',f'{best_bid:.0%}' if best_bid is not None else 'n/a')
                            st.caption(('US BTC UP/DOWN mapping verified by typed market metadata and official US Crypto FAQs.' if mapped else 'LONG/SHORT shown until typed US BTC Up/Down metadata is confirmed.')+' Quotes are indicative and can change before execution.')
                            if abs(long_px+short_px-1)>0.03:
                                st.warning('LONG and SHORT quotes are not complementary; inspect the raw response before interpreting them.')
                        else:
                            st.warning('Quote returned but LONG/SHORT price fields were not readable.')
                        with st.expander('US quote diagnostics · raw BBO response',expanded=False):
                            st.json(quote)
                        st.caption('Official US price to beat: '+(f'${reference:,.2f} from typed market record.' if reference is not None else 'pending publication. No trading signal is issued.'))
                    except Exception as exc:
                        st.warning(f'US SDK BBO unavailable: {type(exc).__name__}: {str(exc)[:240]}')
                        st.caption('A market slug found in event metadata may not be a tradable exchange instrument slug. Inspect the contract details above.')
        else:
            st.caption('US odds pending market mapping; international odds are never substituted.')

        st.subheader('02 · SIGNAL CENTER · MODEL & MARKET')
        st.caption('A normal-return volatility model, NOT a trained or validated predictor. This is a hypothesis to backtest, not a proven advantage.')
        st.html('''<div class="signal-hero"><div class="signal-label">PRIMARY SIGNAL · RESEARCH MODE</div><div class="signal-title">WAIT / OBSERVE</div><div class="signal-sub">No validated trading edge. The indicators and simulations below are exploratory, not an actionable BUY/SELL recommendation.</div></div>''')
        if strike<=0:st.warning('Waiting for the official price to beat before enabling the model.')
        else:
            # Current spot-to-strike, zero drift; proxy volatility. Floors guard against implausible certainty.
            sigma=max(minute_vol,0.00005)*math.sqrt(max(remaining/60,1))
            z=math.log(price/strike)/sigma
            p_up=min(0.995,max(0.005,normal_cdf(z)))
            # uncertainty interval under ± 1 minute-vol discrepancy in observed price, not a confidence interval
            low=normal_cdf(z-1);high=normal_cdf(z+1)
            c1,c2,c3=st.columns(3)
            c1.metric('Illustrative UP probability',f'{p_up:.1%}')
            c2.metric('Illustrative DOWN probability',f'{1-p_up:.1%}')
            c3.metric('Spot minus strike',f'${price-strike:+,.2f}')
            st.write(f'Sensitivity to a one-minute-volatility shift in reference price: UP {low:.1%}–{high:.1%}. This is **not** a statistical confidence interval.')
            st.write(f'EMA 9 vs 21: {"bullish" if ema9>ema21 else "bearish"}; RSI: {rs:.1f}; 5m volume / 20m average: {vol5/vol20:.2f}×. These are descriptive only and are **not** added as untested prediction boosts.')
            fee=st.number_input('Estimated total costs per share (USD, fees + slippage)',min_value=0.0,max_value=0.25,value=0.03,step=0.005,format='%.3f')
            if book_ok:
                rows=[]
                for side,prob in [('UP',p_up),('DOWN',1-p_up)]:
                    ask=asks[side.lower()];edge=prob-ask-fee
                    rows.append({'Side':side,'Model probability':f'{prob:.1%}','Best ask':f'${ask:.3f}','Assumed costs':f'${fee:.3f}','Hypothetical EV/share':f'${edge:+.3f}'})
                st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
                st.warning('NO VERIFIED EDGE / NO BET SIGNAL: model is not calibrated to US BRTI outcomes and quotes may be stale or unavailable at your size. Positive hypothetical EV is not evidence of profitability.')

        st.subheader('02A · SIGNAL STATS · INDEPENDENT METRICS')
        st.caption("Independent Shane's BTC Tracker calculations. Experimental signals; historical win rates are not yet verified.")
        trend = 'LONG' if ema9 > ema21 else 'SHORT' if ema9 < ema21 else 'NEUTRAL'
        # Transparent, explicitly local confluence rubric; never imply parity with the third-party 4.5 scale.
        trend_votes = [ema9 > ema21, rs > 50, float(last['close']) > float(last['open']), vol5 > vol20]
        long_votes = sum(trend_votes)
        short_votes = 4 - long_votes
        conf_side = 'LONG' if long_votes > short_votes else 'SHORT' if short_votes > long_votes else 'MIXED'
        conf_score = max(long_votes, short_votes)
        mc_up = mc_down = None
        if strike > 0:
            # Zero-drift normal return proxy, distinct from the analytic normal CDF above.
            mc_rng = np.random.default_rng(20261102)
            mc_samples = mc_rng.normal(0, max(minute_vol, .00005), (5000, max(1, math.ceil(remaining/60))))
            mc_end = price * np.exp(mc_samples.sum(axis=1) * math.sqrt(max(remaining/60, .1)/max(1, math.ceil(remaining/60))))
            mc_up = float(np.mean(mc_end >= strike))
            mc_down = 1 - mc_up
        blend_up = (p_up + mc_up)/2 if mc_up is not None else None
        blend_down = 1-blend_up if blend_up is not None else None
        r1,r2,r3,r4=st.columns(4)
        r1.metric('Trend (EMA 9/21)',trend)
        r2.metric('Confluence (our 4 reads)',f'{conf_score}/4 · {conf_side}')
        r3.metric('15m UP model (proxy)',f'{p_up:.3f}' if strike>0 else 'n/a')
        r4.metric('15m DOWN model (proxy)',f'{1-p_up:.3f}' if strike>0 else 'n/a')
        r5,r6,r7,r8=st.columns(4)
        r5.metric('MC UP (spot proxy)',f'{mc_up:.3f}' if mc_up is not None else 'n/a')
        r6.metric('MC DOWN (spot proxy)',f'{mc_down:.3f}' if mc_down is not None else 'n/a')
        r7.metric('Blend UP (unvalidated)',f'{blend_up:.3f}' if blend_up is not None else 'n/a')
        r8.metric('Blend DOWN (unvalidated)',f'{blend_down:.3f}' if blend_down is not None else 'n/a')
        if book_ok and blend_up is not None:
            edge_up=blend_up-asks['up']
            edge_down=blend_down-asks['down']
            a,b,c=st.columns(3)
            a.metric('UP edge before fees (proxy)',f'{edge_up:+.3f}')
            b.metric('DOWN edge before fees (proxy)',f'{edge_down:+.3f}')
            c.metric('Desk decision','WAIT')
        else:
            st.caption('Edge unavailable until both ticket prices and a verified price to beat are available.')
        with st.expander('Opening prices and historical win records'):
            st.write('Opening UP/DOWN prices require snapshots at each market start. Historical win rates require saved predictions matched with verified settlement outcomes. No results are fabricated.')

        # Countdown is browser-side; the Streamlit app refreshes approximately every 60 seconds when enabled.
        st.caption("Market data refreshes every 60 seconds when automatic refresh is enabled. The main countdown remains live between updates.")

        st.subheader('02B · MOMENTUM RADAR · LEAN & SWING')
        st.caption('Descriptive price-action and odds signals, not validated forecasts. Checks on each dashboard refresh; Kraken indicators use completed 1-minute candles, so values may remain unchanged between refreshes.')
        DB=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')
        lean_db=sqlite3.connect(DB,timeout=10)
        lean_db.execute('CREATE TABLE IF NOT EXISTS lean_ticks (slug TEXT, captured INTEGER, candle_time INTEGER, spot REAL, up_ask REAL, down_ask REAL, lean TEXT, score INTEGER, swing TEXT, PRIMARY KEY(slug,captured))')
        lean_db.execute('CREATE TABLE IF NOT EXISTS lean_stage (slug TEXT, stage INTEGER, captured INTEGER, stage_end INTEGER, lean TEXT, score INTEGER, swing TEXT, spot REAL, up_ask REAL, down_ask REAL, segment_up INTEGER, PRIMARY KEY(slug,stage))')
        # Directional votes are independent of the official strike.
        close_series=df.close.astype(float)
        ret3=float(close_series.iloc[-1]/close_series.iloc[-4]-1) if len(df)>4 else 0.0
        ret5=float(close_series.iloc[-1]/close_series.iloc[-6]-1) if len(df)>6 else 0.0
        ema_slope=float(df.ema9.iloc[-1]-df.ema9.iloc[-4]) if len(df)>4 else 0.0
        prev_rsi=float(df.rsi14.iloc[-4]) if len(df)>4 else rs
        votes=[('EMA alignment',1 if ema9>ema21 else -1 if ema9<ema21 else 0),('EMA slope',1 if ema_slope>0 else -1 if ema_slope<0 else 0),('3-minute momentum',1 if ret3>0 else -1 if ret3<0 else 0),('RSI above/below 50',1 if rs>50 else -1 if rs<50 else 0),('RSI direction',1 if rs>prev_rsi else -1 if rs<prev_rsi else 0)]
        lean_score=sum(v for _,v in votes)
        lean_label='UP' if lean_score>=2 else 'DOWN' if lean_score<=-2 else 'NEUTRAL'
        lean_strength=abs(lean_score)
        # Swing is an early warning only: opposing short-term momentum and weakening RSI.
        trend_dir=1 if ema9>ema21 else -1 if ema9<ema21 else 0
        momentum_dir=1 if ret3>0 else -1 if ret3<0 else 0
        rsi_dir=1 if rs>prev_rsi else -1 if rs<prev_rsi else 0
        swing_watch=(trend_dir!=0 and momentum_dir==-trend_dir and rsi_dir==-trend_dir)
        swing_label='POTENTIAL REVERSAL' if swing_watch else 'No aligned reversal warning'
        # Compare market asks with a previous observation from this same contract.
        prev=lean_db.execute('SELECT up_ask,down_ask,lean FROM lean_ticks WHERE slug=? AND captured<? ORDER BY captured DESC LIMIT 1',(slug,now)).fetchone()
        up_change=(asks['up']-prev[0]) if prev and asks.get('up') is not None and prev[0] is not None else None
        down_change=(asks['down']-prev[1]) if prev and asks.get('down') is not None and prev[1] is not None else None
        odds_lean='UP strengthening' if up_change is not None and down_change is not None and up_change>0.005 and down_change< -0.005 else 'DOWN strengthening' if up_change is not None and down_change is not None and down_change>0.005 and up_change< -0.005 else 'No clear shift / insufficient history'
        market_disagreement=(odds_lean=='UP strengthening' and lean_label=='DOWN') or (odds_lean=='DOWN strengthening' and lean_label=='UP')
        lean_db.execute('INSERT OR IGNORE INTO lean_ticks VALUES (?,?,?,?,?,?,?,?,?)',(slug,now,int(last['time'].timestamp()),price,asks.get('up'),asks.get('down'),lean_label,lean_score,swing_label))
        stage_idx=min(2,max(0,(now-start)//300))
        lean_db.execute('INSERT OR IGNORE INTO lean_stage (slug,stage,captured,stage_end,lean,score,swing,spot,up_ask,down_ask) VALUES (?,?,?,?,?,?,?,?,?,?)',(slug,stage_idx,now,start+(stage_idx+1)*300,lean_label,lean_score,swing_label,price,asks.get('up'),asks.get('down')))
        # Historical stage resolution: completed Kraken candles, only if exact boundary observations exist.
        close_by_time={int(t.timestamp())+60:float(c) for t,c in zip(df.time,df.close)}
        for old_slug,old_stage,end_time in lean_db.execute('SELECT slug,stage,stage_end FROM lean_stage WHERE segment_up IS NULL').fetchall():
            first=close_by_time.get(end_time-300);final=close_by_time.get(end_time)
            if end_time<=now and first is not None and final is not None:
                lean_db.execute('UPDATE lean_stage SET segment_up=? WHERE slug=? AND stage=?',(int(final>first),old_slug,old_stage))
        lean_db.commit()
        la,lb,lc,ld=st.columns(4)
        la.metric('BTC price-action lean',lean_label)
        lb.metric('Directional agreement',f'{lean_strength}/5')
        lc.metric('Swing watch','WATCH' if swing_watch else 'CLEAR')
        ld.metric('3-minute momentum',f'{ret3:+.3%}')
        st.write(f'**Swing status:** {swing_label}. **Market odds:** {odds_lean}.' + (' **Price/odds disagreement detected.**' if market_disagreement else ''))
        with st.expander('Lean inputs, recent odds changes & historical checks'):
            st.dataframe(pd.DataFrame([{'Indicator':name,'Vote':'UP' if val>0 else 'DOWN' if val<0 else 'NEUTRAL'} for name,val in votes]),hide_index=True,width="stretch")
            st.write(f'UP ask change: {up_change:+.3f}' if up_change is not None else 'UP ask change: waiting for second observation')
            st.write(f'DOWN ask change: {down_change:+.3f}' if down_change is not None else 'DOWN ask change: waiting for second observation')
            hist_lean=pd.read_sql_query('SELECT * FROM lean_stage ORDER BY captured DESC',lean_db)
            resolved=hist_lean.dropna(subset=['segment_up'])
            directional=resolved[resolved.lean.isin(['UP','DOWN'])]
            correct=((directional.lean=='UP')==(directional.segment_up==1)).mean() if len(directional) else None
            x,y,z=st.columns(3)
            x.metric('Saved stage leans',len(hist_lean))
            y.metric('Resolved stage leans',len(directional))
            z.metric('Kraken 5m-stage accuracy',f'{correct:.1%}' if correct is not None else 'Pending')
            st.dataframe(hist_lean.head(30),hide_index=True,width="stretch")
            st.download_button('Export lean history',hist_lean.to_csv(index=False),'btc_lean_history.csv','text/csv')
            st.caption('Each stage records its first observed lean only. Stage accuracy uses Kraken close-to-close 5-minute moves, not official Polymarket outcomes. NEUTRAL calls are excluded. Historical stages outside Kraken candle retention may remain unresolved. Market odds shifts compare successive sampled asks, not trades or true order flow.')
        lean_db.close()

    with right_col:
        st.subheader('03 · PIXEL FORECAST · FIVE 3-MIN STAGES')
        st.caption('3-minute windows show shorter-term movement; the original 5-minute view remains below. These are zero-drift spot-price simulations, not validated directional predictions or trade signals.')
        lookback=st.select_slider('Historical return sample (minutes)',options=[60,120,240,480],value=240)
        samples=np.log(df.close).diff().dropna().tail(lookback).to_numpy()
        rng=np.random.default_rng(42)
        N=8000
        elapsed=(now-start)/60
        def make_segment_forecasts(width, count):
            results=[]
            for i in range(count):
                seg_start=i*width; seg_end=(i+1)*width
                future_start=max(elapsed,seg_start)
                future_minutes=max(0,seg_end-future_start)
                if future_minutes<=0:
                    results.append({'Segment':f'{seg_start}–{seg_end} min','Status':'Completed','P(rise)':'—','Median end price':'—','10–90% end range':'—'})
                    continue
                full=int(future_minutes); fraction=future_minutes-full
                paths=np.zeros(N)
                if full: paths+=rng.choice(samples,size=(N,full),replace=True).sum(axis=1)
                if fraction>0: paths+=rng.choice(samples,size=N,replace=True)*math.sqrt(fraction)
                endings=price*np.exp(paths)
                results.append({'Segment':f'{seg_start}–{seg_end} min','Status':'Current' if seg_start<=elapsed<seg_end else 'Upcoming','P(rise)':f'{float(np.mean(paths>0)):.1%}','Median end price':f'${np.median(endings):,.0f}','10–90% end range':f'${np.quantile(endings,.1):,.0f} – ${np.quantile(endings,.9):,.0f}'})
            return results
        segments_3=make_segment_forecasts(3,5)
        for row_start in (0,3):
            cols=st.columns(3)
            for col, segment in zip(cols,segments_3[row_start:row_start+3]):
                with col:
                    st.markdown(f'**{segment["Segment"]}** · {segment["Status"]}')
                    st.metric('P(rise) · baseline',segment['P(rise)'])
                    st.caption(f'Median end: {segment["Median end price"]}')
        with st.expander('Detailed five-stage (3-minute) forecast table'):
            st.dataframe(pd.DataFrame(segments_3),hide_index=True,width="stretch")
        segments=make_segment_forecasts(5,3)
        with st.expander('Broader trend · three 5-minute forecasts'):
            st.dataframe(pd.DataFrame(segments),hide_index=True,width="stretch")
            st.caption('Retained for comparison with the 3-minute windows; shorter windows can be noisier.')
        st.info('The future segment probabilities are from today’s observed spot, not from a forecast of the price at each segment’s beginning. They are probabilities of net price change over the remaining portion of that segment. A 50/50 reading is expected from the zero-drift baseline and is not an actionable signal.')
        if strike>0:
            full=int(remaining/60);fraction=remaining/60-full
            paths=np.zeros(N)
            if full:paths+=rng.choice(samples,size=(N,full),replace=True).sum(axis=1)
            if fraction>0:paths+=rng.choice(samples,size=N,replace=True)*math.sqrt(fraction)
            outcomes=price*np.exp(paths)
            p_boot=float(np.mean(outcomes>strike))
            st.metric('Simulated P(final Kraken spot above selected reference)',f'{p_boot:.1%}')
            st.caption('This models the ending Kraken spot proxy, not the US BRTI settlement. It is deliberately NOT used to issue a betting recommendation.')
            if book_ok:
                up_gap=p_boot-asks['up'];down_gap=(1-p_boot)-asks['down']
                st.write(f'Before costs, simulated probability minus current ask: UP {up_gap:+.1%}; DOWN {down_gap:+.1%}. These gaps are not proven tradeable edges.')
            st.warning('Entry timing: WAIT / OBSERVE by default. The tool cannot determine whether buying now beats waiting five minutes without a validated forecast of future share prices, settlement data, and transaction costs.')
        else:st.warning('Waiting for the price to beat to show a provisional final-outcome simulation.')


        # Persistent local snapshots; captured once per stage and never overwritten.
        DB=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')
        with st.expander('04 · HIGH SCORE HISTORY · ACCURACY TRACKER',expanded=True):
            try:
                con=sqlite3.connect(DB,timeout=10)
                con.execute('CREATE TABLE IF NOT EXISTS snapshots (slug TEXT, stage INTEGER, captured INTEGER, stage_end INTEGER, p_up REAL, p_segment REAL, up_ask REAL, down_ask REAL, winner TEXT, segment_up INTEGER, PRIMARY KEY(slug,stage))')
                stage=min(2,max(0,(now-start)//300))
                if verified_reference and book_ok and blend_up is not None:
                    sp=float(segments[stage]['P(rise)'].strip('%'))/100 if segments[stage]['Status']=='Current' and segments[stage]['P(rise)']!='—' else None
                    con.execute('INSERT OR IGNORE INTO snapshots (slug,stage,captured,stage_end,p_up,p_segment,up_ask,down_ask) VALUES (?,?,?,?,?,?,?,?)',(slug,stage,now,start+(stage+1)*300,blend_up,sp,asks['up'],asks['down']))
                else:st.caption('Official-result snapshot pending US-verified price to beat and live asks. Proxy calculations are never saved as verified forecasts.')
                close_by_time={int(t.timestamp())+60:float(c) for t,c in zip(df.time,df.close)}
                for ms,si,ce in con.execute('SELECT slug,stage,stage_end FROM snapshots WHERE segment_up IS NULL').fetchall():
                    opening=close_by_time.get(ce-300);closing=close_by_time.get(ce)
                    if ce<=now and opening is not None and closing is not None:
                        con.execute('UPDATE snapshots SET segment_up=? WHERE slug=? AND stage=?',(int(closing>opening),ms,si))
                # US-only: do not infer official settlement from Kraken or international markets.
                con.commit()
                history=pd.read_sql_query('SELECT * FROM snapshots ORDER BY captured DESC',con)
                if len(history):
                    official=history.dropna(subset=['winner','p_up']);segment=history.dropna(subset=['segment_up','p_segment'])
                    a,b,c=st.columns(3);a.metric('Saved stage snapshots',len(history));b.metric('Official results',len(official));c.metric('Final direction accuracy',f'{((official.p_up>=.5)==(official.winner=="UP")).mean():.1%}' if len(official) else 'Pending')
                    summary=[]
                    for i in range(3):
                        r=segment[segment.stage==i]
                        summary.append({'Stage':f'{i*5}–{(i+1)*5}m','Resolved spot-proxy forecasts':len(r),'Accuracy':f'{((r.p_segment>=.5)==(r.segment_up==1)).mean():.1%}' if len(r) else 'Pending'})
                    st.dataframe(pd.DataFrame(summary),hide_index=True,width="stretch")
                    if len(official):
                        st.metric('Brier score (lower is better)',f'{((official.p_up-(official.winner=="UP").astype(int))**2).mean():.3f}')
                        pl=sum((1 if ('UP' if r.p_up>=.5 else 'DOWN')==r.winner else 0)-(r.up_ask if r.p_up>=.5 else r.down_ask) for _,r in official.iterrows())
                        st.metric('Hypothetical one-share P/L before costs',f'${pl:+.2f}')
                    st.dataframe(history.head(40),hide_index=True,width="stretch")
                    st.download_button('Export saved accuracy history',history.to_csv(index=False),'btc_accuracy_history.csv','text/csv')
                else:st.write('No predictions saved yet. Leave the app running to begin collecting snapshots.')
                st.caption('Local SQLite file persists across restarts. Stage results use Kraken 1-minute spot closes, NOT US BRTI. Official results require an explicit resolved winner from Polymarket; otherwise pending. Paper returns exclude fees and slippage. No orders placed.')
                con.close()
            except (sqlite3.Error,OSError) as exc:st.error(f'History database error: {exc}')

        st.markdown('**04 · Historical observation log** · Record observations for later testing; no trades are placed.')
        if 'logs' not in st.session_state:st.session_state.logs=[]
        if st.button('Record current observation'):
            st.session_state.logs.append({'utc':datetime.now(timezone.utc).isoformat(),'slug':slug,'spot_proxy':price,'strike':strike if strike>0 else None,'strike_source':reference_source,'seconds_remaining':remaining,'rsi14':rs,'ema9':ema9,'ema21':ema21,'volatility_1m':minute_vol,'up_ask':asks.get('up'),'down_ask':asks.get('down'),'model_up_probability':p_up if strike>0 else None})
            st.success('Observation added to this session.')
        if st.session_state.logs:
            st.dataframe(pd.DataFrame(st.session_state.logs),width="stretch")
            st.download_button('Download observations CSV',pd.DataFrame(st.session_state.logs).to_csv(index=False),'btc_signal_observations.csv','text/csv')
        st.caption('The countdown updates live; other data refreshes when you reload the page. Session observations may disappear if the server restarts; download the CSV. No API keys are used.')

        st.divider()
        st.markdown('**UTC market window details**')
        st.markdown(f'**Current UTC window:** {datetime.fromtimestamp(start,timezone.utc):%Y-%m-%d %H:%M}–{datetime.fromtimestamp(start+900,timezone.utc):%H:%M} • **Time remaining:** {remaining//60}m {remaining%60}s')
        st.markdown(f'[Open current Polymarket US window](https://polymarket.us/event/{slug})')


    # PIXEL V9 — AUTOMATED RESEARCH ARCHIVE
    # Saves a timestamped sample every dashboard refresh, without treating Kraken
    # prices or a market quote as verified US settlement data.
    st.html('<div class="retro-section">▣ 05 · AUTOMATED US MARKET ARCHIVE // PIXEL V9</div>')
    ARCHIVE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')
    try:
        archive=sqlite3.connect(ARCHIVE,timeout=10)
        archive.execute('''CREATE TABLE IF NOT EXISTS us_market_samples (
          event_slug TEXT NOT NULL, captured INTEGER NOT NULL, market_slug TEXT,
          window_start INTEGER, window_end INTEGER, seconds_left INTEGER,
          us_price_to_beat REAL, kraken_spot REAL, model_up REAL,
          up_long_quote REAL, down_short_quote REAL, best_bid REAL, best_ask REAL,
          quote_status TEXT, PRIMARY KEY(event_slug,captured))''')
        archive.execute('''CREATE TABLE IF NOT EXISTS us_market_results (
          event_slug TEXT PRIMARY KEY, market_slug TEXT, window_end INTEGER,
          official_winner TEXT, verified_at INTEGER, source TEXT,
          status TEXT NOT NULL DEFAULT 'PENDING')''')
        archive.execute('CREATE INDEX IF NOT EXISTS us_samples_by_time ON us_market_samples(captured)')
        # Reuse the live quote already fetched in Market Radar, only when the
        # typed contract identifies BTC Up/Down and the returned slug matches.
        archive_quote=locals().get('quote')
        archive_md=archive_quote.get('marketData',{}) if isinstance(archive_quote,dict) else {}
        if not isinstance(archive_md,dict): archive_md={}
        archive_terms=(full_market or {}).get('assetPriceTerms') or {}
        archive_asset=archive_terms.get('asset') or {}
        archive_mapped=(str(archive_asset.get('symbol','')).lower() in ('btc','xbt')
                        and 'UP_DOWN' in str(archive_terms.get('marketType','')).upper())
        archive_market_slug=(full_market or {}).get('slug')
        archive_quote_ok=bool(archive_mapped and archive_market_slug
                              and archive_md.get('marketSlug')==archive_market_slug)
        def archive_price(field):
            if not archive_quote_ok:return None
            value=archive_md.get(field)
            try:
                v=float(value.get('value') if isinstance(value,dict) else value)
                return v if math.isfinite(v) and 0<=v<=1 else None
            except (TypeError,ValueError,AttributeError):return None
        archive_up=archive_price('longQuote')
        archive_down=archive_price('shortQuote')
        archive_bid=archive_price('bestBid')
        archive_ask=archive_price('bestAsk')
        # Zero-drift research probability. Never store a proxy as official.
        archive_model=None
        if verified_reference and strike>0 and math.isfinite(minute_vol):
            archive_sigma=max(minute_vol,.00005)*math.sqrt(max(remaining/60,1))
            archive_model=min(.995,max(.005,normal_cdf(math.log(price/strike)/archive_sigma)))
        archive.execute('''INSERT OR IGNORE INTO us_market_samples
           (event_slug,captured,market_slug,window_start,window_end,seconds_left,
            us_price_to_beat,kraken_spot,model_up,up_long_quote,down_short_quote,
            best_bid,best_ask,quote_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (slug,now,archive_market_slug,start,start+900,remaining,
             reference if verified_reference else None,price,archive_model,
             archive_up,archive_down,archive_bid,archive_ask,
             'MAPPED' if archive_quote_ok else 'UNVERIFIED'))
        archive.execute('''INSERT OR IGNORE INTO us_market_results
            (event_slug,market_slug,window_end,status) VALUES (?,?,?,'PENDING')''',
            (slug,archive_market_slug,start+900))
        archive.commit()
        # Automatically recheck a few recently completed markets, rate-limited
        # to once every 5 minutes per Streamlit process. The official winner is
        # left pending unless a trustworthy, explicit outcome is returned.
        @st.cache_data(ttl=300,show_spinner=False)
        def inspect_completed_us_market(market_slug):
            return us_full_market(market_slug)
        pending=archive.execute('''SELECT event_slug,market_slug FROM us_market_results
           WHERE status='PENDING' AND window_end<? AND market_slug IS NOT NULL
           ORDER BY window_end DESC LIMIT 5''',(now-60,)).fetchall()
        for old_slug,old_market_slug in pending:
            try:
                completed=inspect_completed_us_market(old_market_slug)
                # A final market record is retained as a status check, not as a
                # winner unless it exposes an explicit, documented winner field.
                explicit=completed.get('winningOutcome') or completed.get('winningSide')
                status=str(completed.get('state') or completed.get('status') or '').upper()
                if status in ('SETTLED','RESOLVED','MARKET_STATE_SETTLED','MARKET_STATE_RESOLVED') and isinstance(explicit,str) and explicit.upper() in ('UP','DOWN'):
                    archive.execute('''UPDATE us_market_results SET official_winner=?,verified_at=?,source=?,status='VERIFIED'
                       WHERE event_slug=?''',(explicit.upper(),now,'US full market explicit winningOutcome/winningSide',old_slug))
            except Exception:
                pass # API outages never overwrite or fabricate results
        archive.commit()
        counts=archive.execute('''SELECT COUNT(*),COUNT(DISTINCT event_slug),
            SUM(CASE WHEN model_up IS NOT NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN up_long_quote IS NOT NULL THEN 1 ELSE 0 END)
            FROM us_market_samples''').fetchone()
        verified_count=archive.execute("SELECT COUNT(*) FROM us_market_results WHERE status='VERIFIED'").fetchone()[0]
        a,b,c,d=st.columns(4)
        a.metric('Saved refresh samples',counts[0]);b.metric('Markets tracked',counts[1])
        c.metric('Model samples',counts[2] or 0);d.metric('Verified outcomes',verified_count)
        st.caption('Automatically records one observation per refresh. US reference and mapped quotes are stored only when verified in the API. Kraken spot is a separate research feed. No orders are placed.')
        recent=pd.read_sql_query('''SELECT datetime(captured,'unixepoch') AS utc,
          event_slug,seconds_left,us_price_to_beat,kraken_spot,model_up,
          up_long_quote,down_short_quote,quote_status
          FROM us_market_samples ORDER BY captured DESC LIMIT 100''',archive)
        with st.expander('Recent archived observations and CSV export'):
            st.dataframe(recent,hide_index=True,width="stretch")
            st.download_button('Export recent samples CSV',recent.to_csv(index=False),
                               'btc_us_market_samples.csv','text/csv',key='v9_export_samples')
        outcomes=pd.read_sql_query('SELECT * FROM us_market_results ORDER BY window_end DESC LIMIT 100',archive)
        with st.expander('US settlement verification queue'):
            st.dataframe(outcomes,hide_index=True,width="stretch")
            st.caption('Completed markets remain PENDING unless the US API explicitly identifies a winner. No Kraken-derived winners or assumed settlement prices are counted as official.')
        if verified_count:
            evaluation=pd.read_sql_query('''SELECT s.event_slug,s.model_up,r.official_winner,
              s.up_long_quote,s.down_short_quote FROM us_market_samples s
              JOIN us_market_results r ON s.event_slug=r.event_slug
              WHERE r.status='VERIFIED' AND s.model_up IS NOT NULL
              AND s.captured=(SELECT MIN(t.captured) FROM us_market_samples t
                  WHERE t.event_slug=s.event_slug AND t.model_up IS NOT NULL)''',archive)
            if len(evaluation):
                actual=(evaluation.official_winner=='UP').astype(float)
                brier=float(((evaluation.model_up-actual)**2).mean())
                accuracy=float(((evaluation.model_up>=.5)==(actual==1)).mean())
                st.write(f'**First valid sample per settled market:** {len(evaluation)} · Direction accuracy {accuracy:.1%} · Brier score {brier:.3f}.')
        archive.close()
    except (sqlite3.Error,OSError) as exc:
        st.error(f'Automated archive unavailable: {exc}')



    st.html('<div class="retro-section">▣ 06 · PERMANENT CLOUD HISTORY // PIXEL V13.5 + 24/7</div>')
    if not CLOUD_READY:
        st.warning("Supabase not configured here. Set SUPABASE_URL and SUPABASE_KEY in Streamlit secrets.")
    else:
        try:
            cloud_request("POST","btc_markets",
                params={"on_conflict":"market_slug"},
                payload={"market_slug":slug,"window_start":utc_iso(start),
                         "window_end":utc_iso(start+900),
                         "price_to_beat":reference if verified_reference else None},
                prefer="resolution=merge-duplicates,return=minimal")
            if verified_reference and reference and 'final_display' in globals():
                archive_quote=locals().get("quote")
                quote_md=archive_quote.get("marketData",{}) if isinstance(archive_quote,dict) else {}
                if not isinstance(quote_md,dict):quote_md={}
                quote_market=quote_md.get("marketSlug")
                confirmed_contract=(full_market or {}).get("slug")
                terms=(full_market or {}).get("assetPriceTerms") or {}
                asset=terms.get("asset") or {}
                mapped=(str(asset.get("symbol","")).lower() in ("btc","xbt") and
                        any(t in str(terms.get("marketType","")).upper() for t in ("UPDOWN","UP_DOWN")))
                def cloud_quote(field):
                    if not (mapped and quote_market and quote_market==confirmed_contract):
                        return None
                    raw=quote_md.get(field)
                    try:
                        number=float(raw.get("value") if isinstance(raw,dict) else raw)
                        return number if math.isfinite(number) and 0<=number<=1 else None
                    except (TypeError,ValueError,AttributeError):
                        return None
                cloud_request("POST","btc_predictions",
                    params={"on_conflict":"market_slug,recorded_at"},
                    payload={"market_slug":slug,"recorded_at":utc_iso(now),
                             "seconds_remaining":remaining,"kraken_spot":price,
                             "price_to_beat":reference,
                             "predicted_up_probability":float(final_display),
                             "predicted_down_probability":float(1-final_display),
                             "market_up_quote":cloud_quote("longQuote"),
                             "market_down_quote":cloud_quote("shortQuote"),
                             "model_version":"Pixel V13.3"},
                    prefer="resolution=ignore-duplicates,return=minimal")
            st.caption("Cloud market/prediction writes remain active. Historical reports and settlement scans are on demand to keep live refreshes responsive.")
            run_cloud_diagnostics = st.checkbox(
                "Load detailed cloud history and settlement diagnostics (slower)",
                value=False, key="run_cloud_diagnostics")
            if run_cloud_diagnostics:
                @st.cache_data(ttl=300,show_spinner=False)
                def cloud_pending_markets():
                    return cloud_request("GET","btc_markets",params={
                        "select":"market_slug,window_end","settlement_status":"eq.PENDING",
                        "window_end":"lt."+utc_iso(int(time.time())-60),
                        "order":"window_end.desc","limit":"5"})
                # Polymarket US documents /v1/markets/{slug}/settlement as a numeric
                # settlement price. It does not document that 0 or 1 maps to BTC UP/DOWN.
                # Therefore a numeric response is diagnostic evidence only, not a winner.
                @st.cache_data(ttl=300,show_spinner=False)
                def official_settlement_diagnostic(contract_slug):
                    return us_get('/v1/markets/'+contract_slug+'/settlement')

                def safe_market_diagnostics(record):
                    # Only market metadata, never credentials, account data, or request headers.
                    if not isinstance(record,dict):
                        return {"response_type":type(record).__name__}
                    interesting=("state","status","result","outcome","winner","settle","resolution","side","contract","assetPriceTerms")
                    return {str(k):str(v)[:600] for k,v in record.items()
                            if any(token in str(k).lower() for token in interesting)}

                def side_mapping_evidence(market, settlement):
                    """Diagnostic only: a 0/1 settlement is not an UP/DOWN winner without a documented mapping."""
                    if not isinstance(market,dict):
                        return 'Market details unavailable'
                    fields=('marketSides','sides','outcomes','contracts','instrument','assetPriceTerms',
                            'longSide','shortSide','yesSide','noSide','description','rules','title')
                    available={k:market[k] for k in fields if k in market}
                    if not available:
                        return 'No explicit side definitions in market response'
                    return str(available)[:1800]

                settlement_diagnostics=[]
                for item in cloud_pending_markets():
                    old_slug=item["market_slug"]
                    entry={"Event":old_slug,"Contract":"unresolved",
                           "API state":"unknown","Settlement price":"unavailable",
                           "Winner":"PENDING","Market fields":"not retrieved",
                           "Settlement response":"not retrieved","Side mapping evidence":"not retrieved","Check note":""}
                    try:
                        _,old_contract,_=us_discover(old_slug)
                        contract=(old_contract or {}).get("slug")
                        if not contract:
                            settlement_diagnostics.append(entry)
                            continue
                        entry["Contract"]=contract
                        completed=us_full_market(contract)
                        state=str(completed.get("state") or completed.get("status") or "unknown").upper()
                        entry["API state"]=state
                        entry["Market fields"]=str(safe_market_diagnostics(completed))[:1200]
                        entry["Side mapping evidence"]=side_mapping_evidence(completed,None)
                        try:
                            settlement=official_settlement_diagnostic(contract)
                            entry["Settlement response"]=str(safe_market_diagnostics(settlement))[:1200]
                            if isinstance(settlement,dict):
                                entry["Settlement price"]=str(settlement.get("settlement","unavailable"))
                        except Exception as settle_exc:
                            entry["Settlement response"]="Unavailable: "+type(settle_exc).__name__
                        # Conservative verification: the full official market must
                        # explicitly identify an UP or DOWN winner and be final.
                        explicit=completed.get("winningOutcome") or completed.get("winningSide")
                        if (state in ("SETTLED","RESOLVED","MARKET_STATE_SETTLED","MARKET_STATE_RESOLVED")
                            and isinstance(explicit,str) and explicit.upper() in ("UP","DOWN")):
                            cloud_request("PATCH","btc_markets",
                                params={"market_slug":"eq."+old_slug,"settlement_status":"eq.PENDING"},
                                payload={"official_winner":explicit.upper(),
                                         "settlement_status":"VERIFIED","settled_at":utc_iso(now),
                                         "updated_at":utc_iso(now)},prefer="return=minimal")
                            entry["Winner"]=explicit.upper()+" (verified)"
                        if entry["Winner"]=="PENDING":
                            entry["Check note"]="No documented explicit final UP/DOWN winner identified"
                    except Exception as exc:
                        entry["API state"]="Lookup unavailable: "+type(exc).__name__
                        entry["Check note"]=str(exc)[:180]
                    settlement_diagnostics.append(entry)
                @st.cache_data(ttl=60,show_spinner=False)
                def cloud_counts():
                    markets=cloud_request("GET","btc_markets",params={
                        "select":"market_slug,settlement_status","limit":"1000"})
                    preds=cloud_request("GET","btc_predictions",params={
                        "select":"market_slug,recorded_at,predicted_up_probability,seconds_remaining",
                        "order":"recorded_at.desc","limit":"30"})
                    return markets,preds
                cloud_markets,cloud_preds=cloud_counts()
                x,y,z=st.columns(3)
                x.metric("Cloud markets tracked",len(cloud_markets))
                y.metric("Verified US settlements",sum(m.get("settlement_status")=="VERIFIED" for m in cloud_markets))
                z.metric("Recent saved predictions",len(cloud_preds))
                st.success("Supabase connected. DigitalOcean collects independently; this dashboard may also save observations while open.")
                with st.expander("Recent cloud predictions"):
                    if cloud_preds:
                        st.dataframe(pd.DataFrame(cloud_preds),hide_index=True,width="stretch")
                    else: st.caption("No cloud predictions saved yet.")
                # Read-only explorer of samples collected by DigitalOcean and Streamlit.
                @st.cache_data(ttl=60,show_spinner=False)
                def cloud_collector_history():
                    records=[]
                    for offset in (0,1000,2000):
                        batch=cloud_request("GET","btc_predictions",params={
                            "select":"market_slug,recorded_at,seconds_remaining,kraken_spot,price_to_beat,predicted_up_probability,predicted_down_probability,model_version",
                            "order":"recorded_at.desc","limit":"1000","offset":str(offset)})
                        records.extend(batch)
                        if len(batch)<1000: break
                    return pd.DataFrame(records)

                with st.expander("24/7 collector history · DigitalOcean + dashboard",expanded=True):
                    st.caption("Read-only Supabase history. The collector runs on DigitalOcean; opening this page is not required for collection. Data may be up to 60 seconds behind.")
                    collector_history=cloud_collector_history()
                    if collector_history.empty:
                        st.info("No saved prediction records found in Supabase yet.")
                    else:
                        h=collector_history.copy()
                        h["recorded_at"]=pd.to_datetime(h["recorded_at"],utc=True,errors="coerce")
                        h=h.dropna(subset=["recorded_at"])
                        for field in ("kraken_spot","price_to_beat","predicted_up_probability","seconds_remaining"):
                            h[field]=pd.to_numeric(h[field],errors="coerce")
                        h=h.sort_values("recorded_at")
                        latest=h.iloc[-1]
                        sample_age=(pd.Timestamp.now(tz="UTC")-latest["recorded_at"]).total_seconds()
                        a,b,c,d=st.columns(4)
                        a.metric("Loaded predictions",f"{len(h):,}")
                        b.metric("Markets represented",f"{h.market_slug.nunique():,}")
                        c.metric("Latest record (UTC)",latest["recorded_at"].strftime("%b %d %H:%M:%S"))
                        d.metric("Latest sample age",f"{max(0,int(sample_age))} sec")
                        if sample_age>180:
                            st.warning("Latest saved prediction is over 3 minutes old. Check the DigitalOcean service logs if collection should be active.")
                        st.caption("The view loads up to the latest 3,000 records. 'Loaded predictions' is not the all-time database total. Multiple observations from one market are not independent outcomes.")
                        model_choices=sorted(h["model_version"].dropna().astype(str).unique().tolist())
                        chosen_models=st.multiselect("Model versions",model_choices,default=model_choices,key="cloud_model_versions")
                        h=h[h["model_version"].isin(chosen_models)]
                        market_choices=h["market_slug"].dropna().unique().tolist()[::-1]
                        selected_market=st.selectbox("Market window",["All loaded markets"]+market_choices,key="cloud_market_window")
                        if selected_market!="All loaded markets":
                            h=h[h["market_slug"]==selected_market]
                        if h.empty:
                            st.info("No records match these filters.")
                        else:
                            chart_data=h.set_index("recorded_at")[["predicted_up_probability","predicted_down_probability"]].rename(columns={
                                "predicted_up_probability":"Model UP","predicted_down_probability":"Model DOWN"})
                            st.markdown("**Experimental model probability over time**")
                            st.line_chart(chart_data,width="stretch")
                            st.caption("Probabilities are uncalibrated Kraken-based research estimates, not verified Polymarket win probabilities.")
                            st.markdown("**Kraken spot and US price-to-beat (USD)**")
                            st.line_chart(h.set_index("recorded_at")[["kraken_spot","price_to_beat"]].rename(columns={
                                "kraken_spot":"Kraken spot","price_to_beat":"US price to beat"}),width="stretch")
                            shown=h.sort_values("recorded_at",ascending=False)
                            st.dataframe(shown.head(200),hide_index=True,width="stretch")
                            st.download_button("Export filtered cloud predictions CSV",shown.to_csv(index=False).encode("utf-8"),
                                "btc_collector_history.csv","text/csv",key="export_cloud_collector")
                            st.caption("Official settlement accuracy remains pending until separately verified UP/DOWN results are available. This view does not score unresolved markets.")
                with st.expander("Official settlement verification queue",expanded=True):
                    st.caption("Diagnostic V13.1: inspect official market state, selected market fields, and settlement response. Numeric settlement prices are NOT treated as payout odds or UP/DOWN winners. Rechecks up to five recent pending markets per refresh cycle.")
                    if settlement_diagnostics:
                        st.dataframe(pd.DataFrame(settlement_diagnostics),hide_index=True,width="stretch")
                    else:
                        st.info("No completed markets waiting for verification yet.")
                with st.expander("Verified forecast accuracy by 3-minute stage",expanded=True):
                    verified_rows=cloud_request("GET","btc_markets",params={
                        "select":"market_slug,official_winner",
                        "settlement_status":"eq.VERIFIED","official_winner":"in.(UP,DOWN)",
                        "limit":"1000"})
                    if not verified_rows:
                        st.info("No officially verified UP/DOWN outcomes yet. Accuracy is pending, not zero percent.")
                    else:
                        winner_map={r["market_slug"]:r["official_winner"] for r in verified_rows}
                        pred_rows=[]
                        for event_id in winner_map:
                            pred_rows.extend(cloud_request("GET","btc_predictions",params={
                                "select":"market_slug,recorded_at,seconds_remaining,predicted_up_probability",
                                "market_slug":"eq."+event_id,
                                "predicted_up_probability":"not.is.null",
                                "order":"recorded_at.asc","limit":"1000"}))
                        stage_results=[]
                        if pred_rows:
                            hist=pd.DataFrame(pred_rows)
                            hist["stage"]=( (900-pd.to_numeric(hist.seconds_remaining,errors="coerce")).clip(0,899)//180 ).astype(int)
                            hist=hist.sort_values("recorded_at").drop_duplicates(["market_slug","stage"],keep="first")
                            hist["actual_up"]=hist.market_slug.map(winner_map).eq("UP").astype(int)
                            hist["p"]=pd.to_numeric(hist.predicted_up_probability,errors="coerce")
                            hist=hist.dropna(subset=["p"])
                            for stage_idx, group in hist.groupby("stage"):
                                stage_results.append({"Elapsed stage":f"{stage_idx*3}–{(stage_idx+1)*3} min",
                                    "Independent markets":len(group),
                                    "Direction accuracy":f"{((group.p>=.5)==(group.actual_up==1)).mean():.1%}",
                                    "Brier score":round(float(((group.p-group.actual_up)**2).mean()),4)})
                        if stage_results:
                            st.dataframe(pd.DataFrame(stage_results),hide_index=True,width="stretch")
                            st.caption("One earliest recorded prediction per verified market per stage; no unverified or current market results included. Research estimates are not validated trading probabilities.")
                        else:
                            st.info("Verified outcomes exist, but no eligible predictions have been matched yet.")
                st.caption('Pixel V13.3 includes the early-lean panel and next-window spot-direction preflight. The settlement queue also exposes available side mapping evidence. Numeric 0/1 settlement values remain diagnostic until a documented mapping confirms what they mean.')
                st.caption("Cloud history survives redeploys. The DigitalOcean collector runs independently; dashboard-only research features still require an active Streamlit session. Outcomes remain PENDING until the US API explicitly confirms a winner.")
        except (RuntimeError,requests.RequestException,ValueError,TypeError) as cloud_exc:
            st.error("Cloud archive error: "+str(cloud_exc)[:240])
            st.caption("Check Streamlit Secrets and the Supabase tables. The local tracker remains available.")
