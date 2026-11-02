import json, math, time, sqlite3, os
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Shane's BTC Tracker", layout='wide')
st.markdown("""<style>
.stApp {background: #0b1019; color: #e9eff9;}
.block-container {max-width: 1720px; padding: .35rem .85rem .9rem;}
h1,h2,h3 {color: #edf4ff !important; letter-spacing: -.025em;}
[data-testid="stMetric"] {background: #151e2d; border: 1px solid #29374b; border-radius: 8px; padding: 5px 8px;}
[data-testid="stMetricLabel"] {color: #9dafc8;}
[data-testid="stMetricValue"] {color: #edf4ff;}
[data-testid="stDataFrame"] {border: 1px solid #29374b; border-radius: 12px; overflow: hidden;}
.stButton button, .stDownloadButton button {background: #233550; color: white; border-radius: 10px; border: 1px solid #3a526f;}
hr {border-color: #29374b;}
.signal-hero {background: linear-gradient(120deg,#172236,#111b2a); border:1px solid #34445e; padding: 7px 10px; border-radius: 9px; margin: 3px 0 7px;}
.signal-label {color:#9dafc8; font-size:12px; letter-spacing:2px; font-weight:700;}
.signal-title {font-size:19px; font-weight:800; color:#f0b966; line-height:1.3;}
.signal-sub {color:#aebed2; font-size:12px;}

/* compact density */
[data-testid="stVerticalBlock"] {gap: .24rem;}
[data-testid="stHorizontalBlock"] {gap: .35rem;}
[data-testid="stMetricValue"] {font-size: 1.08rem; line-height:1.15;}
[data-testid="stMetricLabel"] {font-size: .68rem;}
[data-testid="stMetricDelta"] {font-size: .7rem;}
h1 {font-size:1.2rem!important;} h2 {font-size:1rem!important;} h3 {font-size:.88rem!important; margin: .2rem 0!important;}
p, .stCaption, [data-testid="stCaptionContainer"] {font-size: .77rem; line-height:1.25;}
[data-testid="stAlert"] {padding: .42rem .7rem;}
[data-testid="stExpander"] {border-radius:8px;}
[data-testid="stNumberInput"] input {min-height: 32px;}
[data-testid="stDataFrame"] {font-size: .76rem;}
hr {margin:.2rem 0!important;}
section[data-testid='stSidebar'] {min-width: 230px;}
[data-testid='stMetric'] {min-width:0;}
[data-testid='stMetricValue'] {overflow-wrap:anywhere;}

</style>""", unsafe_allow_html=True)
st.markdown("### ◉ SHANE'S BTC TRACKER")
st.caption('LIVE SIGNAL DESK  /  15-MINUTE BTC  /  20-SECOND REFRESH  ·  Research only')
st_autorefresh(interval=20_000, key='auto_refresh')

@st.cache_data(ttl=15)
def get_json(url, params=None):
    r=requests.get(url,params=params,timeout=12,headers={'User-Agent':'BTCSignalLab/0.1'})
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
slug=f'btc-updown-15m-{start}'
# Browser-side UTC-aligned countdown. Runs continuously without refreshing Streamlit.
# Polymarket BTC 15m market slugs follow UTC epoch 900-second boundaries.
components.html("""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
*{box-sizing:border-box}body{margin:0;background:transparent;color:#edf4ff;font-family:system-ui,-apple-system,sans-serif}
.panel{background:linear-gradient(110deg,#172236,#111b2a);border:1px solid #34445e;border-radius:9px;padding:8px 12px}
.top{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}.label{font-size:11px;letter-spacing:1.7px;color:#9dafc8;font-weight:700}
.time{font-size:30px;font-variant-numeric:tabular-nums;font-weight:800;letter-spacing:1px}.stage{font-size:13px;color:#f0b966;font-weight:700}
.track{display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:5px}.seg{height:5px;border-radius:6px;background:#2c3c52;overflow:hidden}.fill{height:100%;width:0;background:#42d99a;transition:width .2s linear}
.meta{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:4px;color:#9dafc8;font-size:12px}
</style></head><body><div class="panel"><div class="top"><div><div class="label">POLYMARKET · BTC 15-MINUTE WINDOW</div><div id="timer" class="time">--:--</div></div><div><div id="stage" class="stage">Syncing…</div><div id="window" style="font-size:12px;color:#9dafc8;margin-top:6px"></div></div></div>
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
""",height=108,scrolling=False)
st.caption('Timer follows your computer clock and UTC 15-minute boundaries; verify the active market on Polymarket. Other data updates when you refresh.')
market=None; error=None
try:
    data=get_json('https://gamma-api.polymarket.com/markets',{'slug':slug})
    market=data[0] if data else None
except Exception as exc:error=str(exc)
if error:st.warning(f'Polymarket data unavailable: {error}')
if not market:st.warning('Current market was not found. Market odds are unavailable; no edge assessment will be shown.')

try: df=candles()
except Exception as exc:
    st.error(f'BTC candle feed unavailable: {exc}. Cannot calculate indicators.');st.stop()
if len(df)<50:st.error('Not enough complete candles');st.stop()
last=df.iloc[-1]; price=float(last['close']); df['ema9']=df.close.ewm(span=9,adjust=False).mean();df['ema21']=df.close.ewm(span=21,adjust=False).mean();df['rsi14']=rsi(df.close)
returns=np.log(df.close).diff().dropna(); minute_vol=float(returns.tail(120).std()); rv=minute_vol*math.sqrt(max(remaining/60,0.25)); ema9=float(df.ema9.iloc[-1]);ema21=float(df.ema21.iloc[-1]);rs=float(df.rsi14.iloc[-1]);
vol20=float(df.volume.tail(20).mean());vol5=float(df.volume.tail(5).mean());
# Gamma may publish priceToBeat with a delay. Never substitute a Kraken spot quote.
@st.cache_data(ttl=10)
def get_reference_from_gamma(market_slug):
    candidates=[]
    events=get_json('https://gamma-api.polymarket.com/events',{'slug':market_slug})
    if isinstance(events,list): candidates.extend(events)
    elif isinstance(events,dict): candidates.append(events)
    markets=get_json('https://gamma-api.polymarket.com/markets',{'slug':market_slug})
    if isinstance(markets,list): candidates.extend(markets)
    elif isinstance(markets,dict): candidates.append(markets)
    for obj in candidates:
        if not isinstance(obj,dict): continue
        for holder in (obj.get('eventMetadata'), obj.get('metadata'), obj):
            if isinstance(holder,str):
                try: holder=json.loads(holder)
                except (ValueError,TypeError): continue
            if not isinstance(holder,dict): continue
            for key in ('priceToBeat','price_to_beat'):
                try:
                    value=float(holder.get(key))
                    if math.isfinite(value) and value>0: return value
                except (TypeError,ValueError): pass
    return None

# Reference provenance matters: Gamma values are market-supplied; Kraken is NOT.
# An automatic spot proxy keeps exploratory charts usable without claiming verification.
strike=0.0
reference=None
reference_source='Unavailable'
try:
    reference=get_reference_from_gamma(slug)
except Exception as exc:
    st.caption(f'Polymarket metadata lookup failed: {exc}')
if reference is not None:
    strike=reference
    reference_source='Gamma market metadata'
    st.success(f'Polymarket price to beat: ${strike:,.2f} · {reference_source} · {slug}')
else:
    st.warning('Polymarket has not provided a verified price to beat for this window. An exchange spot price is NOT the Chainlink settlement reference.')
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
verified_reference=(reference is not None)

# Two-column workstation: signals/market left, forecasts/history right.
left_col, right_col = st.columns([1, 1], gap="medium")
with left_col:
    st.subheader('01 · Polymarket ticket prices')
    asks={}; book_ok=False
    if market:
        tokens=parse_array(market.get('clobTokenIds')); outcomes=parse_array(market.get('outcomes'))
        st.write('Market:',market.get('question','Unknown'))
        if len(tokens)==len(outcomes):
            for outcome,token in zip(outcomes,tokens):
                try:
                    book=get_json('https://clob.polymarket.com/book',{'token_id':token})
                    ask_values=[float(x['price']) for x in book.get('asks',[]) if float(x.get('size',0))>0]
                    asks[outcome.lower()]=min(ask_values) if ask_values else None
                except Exception as exc:st.warning(f'{outcome} book unavailable: {exc}')
            book_ok=all(asks.get(k) is not None for k in ('up','down'))
        else:st.warning('Token/outcome mapping unavailable')
        if book_ok:
            a,b=st.columns(2);a.metric('UP best ask',f'{asks["up"]:.3f}');b.metric('DOWN best ask',f'{asks["down"]:.3f}')
    else:st.write('No live orderbook available.')

    st.subheader('02 · Model blend and market comparison')
    st.caption('A normal-return volatility model, NOT a trained or validated predictor. This is a hypothesis to backtest, not a proven advantage.')
    st.markdown('''<div class="signal-hero"><div class="signal-label">PRIMARY SIGNAL · RESEARCH MODE</div><div class="signal-title">WAIT / OBSERVE</div><div class="signal-sub">No validated trading edge. The indicators and simulations below are exploratory, not an actionable BUY/SELL recommendation.</div></div>''', unsafe_allow_html=True)
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
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.warning('NO VERIFIED EDGE / NO BET SIGNAL: model is not calibrated to Chainlink outcomes and quotes may be stale or unavailable at your size. Positive hypothetical EV is not evidence of profitability.')

    st.subheader('02A · Signal desk · Independent model metrics')
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

    # Countdown is browser-side; the Streamlit app itself refreshes every 20 seconds.
    components.html("""
    <style>body{margin:0;background:transparent;color:#dce7f8;font:13px system-ui,-apple-system,sans-serif}.bar{background:#151e2d;border:1px solid #34445e;border-radius:8px;padding:9px 12px;display:flex;align-items:center;justify-content:space-between;gap:12px}.label{color:#9dafc8}.count{color:#49dda6;font-size:20px;font-weight:750;font-variant-numeric:tabular-nums}</style>
    <div class="bar"><div><strong>LEAN &amp; SWING UPDATE</strong><div class="label">Automatic dashboard refresh every 20 seconds</div></div><div><span class="count" id="count">20s</span><div class="label" id="state">Next refresh</div></div></div>
    <script>const begun=performance.now();function tick(){let left=Math.max(0,20-(performance.now()-begun)/1000);document.getElementById('count').textContent=left.toFixed(0)+'s';if(left===0)document.getElementById('state').textContent='Refresh due…';}tick();setInterval(tick,200);</script>
    """,height=70,scrolling=False)

    st.subheader('02B · Live lean & swing watch')
    st.caption('Descriptive price-action and odds signals, not validated forecasts. Checks on each 20-second app refresh; Kraken indicators use completed 1-minute candles, so values may remain unchanged between refreshes.')
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
        st.dataframe(pd.DataFrame([{'Indicator':name,'Vote':'UP' if val>0 else 'DOWN' if val<0 else 'NEUTRAL'} for name,val in votes]),hide_index=True,use_container_width=True)
        st.write(f'UP ask change: {up_change:+.3f}' if up_change is not None else 'UP ask change: waiting for second observation')
        st.write(f'DOWN ask change: {down_change:+.3f}' if down_change is not None else 'DOWN ask change: waiting for second observation')
        hist_lean=pd.read_sql_query('SELECT * FROM lean_stage ORDER BY captured DESC',lean_db)
        resolved=hist_lean.dropna(subset=['segment_up'])
        directional=resolved[resolved.lean.isin(['UP','DOWN'])]
        correct=((directional.lean=='UP')==(directional.segment_up==1)).mean() if len(directional) else None
        x,y,z=st.columns(3)
        x.metric('Saved stage leans',len(hist_lean))
        y.metric('Resolved stage leans',len(directional))
        z.metric('Kraken stage accuracy',f'{correct:.1%}' if correct is not None else 'Pending')
        st.dataframe(hist_lean.head(30),hide_index=True,use_container_width=True)
        st.download_button('Export lean history',hist_lean.to_csv(index=False),'btc_lean_history.csv','text/csv')
        st.caption('Each stage records its first observed lean only. Stage accuracy uses Kraken close-to-close 5-minute moves, not official Polymarket outcomes. NEUTRAL calls are excluded. Historical stages outside Kraken candle retention may remain unresolved. Market odds shifts compare successive sampled asks, not trades or true order flow.')
    lean_db.close()

with right_col:
    st.subheader('03 · Five 3-minute forecasts · primary view')
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
        st.dataframe(pd.DataFrame(segments_3),hide_index=True,use_container_width=True)
    segments=make_segment_forecasts(5,3)
    with st.expander('Broader trend · three 5-minute forecasts'):
        st.dataframe(pd.DataFrame(segments),hide_index=True,use_container_width=True)
        st.caption('Retained for comparison with the 3-minute windows; shorter windows can be noisier.')
    st.info('The future segment probabilities are from today’s observed spot, not from a forecast of the price at each segment’s beginning. They are probabilities of net price change over the remaining portion of that segment. A 50/50 reading is expected from the zero-drift baseline and is not an actionable signal.')
    if strike>0:
        full=int(remaining/60);fraction=remaining/60-full
        paths=np.zeros(N)
        if full:paths+=rng.choice(samples,size=(N,full),replace=True).sum(axis=1)
        if fraction>0:paths+=rng.choice(samples,size=N,replace=True)*math.sqrt(fraction)
        outcomes=price*np.exp(paths)
        p_boot=float(np.mean(outcomes>strike))
        st.metric('Simulated P(final BTC spot proxy above official price to beat)',f'{p_boot:.1%}')
        st.caption('This models the ending Kraken spot proxy, not the Chainlink TWAP settlement. It is deliberately NOT used to issue a betting recommendation.')
        if book_ok:
            up_gap=p_boot-asks['up'];down_gap=(1-p_boot)-asks['down']
            st.write(f'Before costs, simulated probability minus current ask: UP {up_gap:+.1%}; DOWN {down_gap:+.1%}. These gaps are not proven tradeable edges.')
        st.warning('Entry timing: WAIT / OBSERVE by default. The tool cannot determine whether buying now beats waiting five minutes without a validated forecast of future share prices, settlement data, and transaction costs.')
    else:st.warning('Waiting for the price to beat to show a provisional final-outcome simulation.')


    # Persistent local snapshots; captured once per stage and never overwritten.
    DB=os.path.join(os.path.dirname(os.path.abspath(__file__)),'btc_signal_history.sqlite3')
    with st.expander('04 · Historical accuracy tracker (persistent)',expanded=True):
        try:
            con=sqlite3.connect(DB,timeout=10)
            con.execute('CREATE TABLE IF NOT EXISTS snapshots (slug TEXT, stage INTEGER, captured INTEGER, stage_end INTEGER, p_up REAL, p_segment REAL, up_ask REAL, down_ask REAL, winner TEXT, segment_up INTEGER, PRIMARY KEY(slug,stage))')
            stage=min(2,max(0,(now-start)//300))
            if verified_reference and book_ok and blend_up is not None:
                sp=float(segments[stage]['P(segment rises)'].strip('%'))/100 if segments[stage]['Status']=='Current' else None
                con.execute('INSERT OR IGNORE INTO snapshots (slug,stage,captured,stage_end,p_up,p_segment,up_ask,down_ask) VALUES (?,?,?,?,?,?,?,?)',(slug,stage,now,start+(stage+1)*300,blend_up,sp,asks['up'],asks['down']))
            else:st.caption('Official-result snapshot pending Gamma-verified price to beat and live asks. Proxy calculations are never saved as verified forecasts.')
            close_by_time={int(t.timestamp())+60:float(c) for t,c in zip(df.time,df.close)}
            for ms,si,ce in con.execute('SELECT slug,stage,stage_end FROM snapshots WHERE segment_up IS NULL').fetchall():
                opening=close_by_time.get(ce-300);closing=close_by_time.get(ce)
                if ce<=now and opening is not None and closing is not None:
                    con.execute('UPDATE snapshots SET segment_up=? WHERE slug=? AND stage=?',(int(closing>opening),ms,si))
            for (ms,) in con.execute('SELECT DISTINCT slug FROM snapshots WHERE winner IS NULL AND stage_end<? LIMIT 12',(now,)).fetchall():
                try:
                    old=get_json('https://gamma-api.polymarket.com/markets',{'slug':ms})
                    m=old[0] if old else {}
                    tokens=m.get('tokens',[])
                    wins=[t.get('outcome','').upper() for t in tokens if isinstance(t,dict) and t.get('winner') is True] if isinstance(tokens,list) else []
                    if m.get('closed') and len(wins)==1 and wins[0] in ('UP','DOWN'):
                        con.execute('UPDATE snapshots SET winner=? WHERE slug=?',(wins[0],ms))
                except Exception:pass
            con.commit()
            history=pd.read_sql_query('SELECT * FROM snapshots ORDER BY captured DESC',con)
            if len(history):
                official=history.dropna(subset=['winner','p_up']);segment=history.dropna(subset=['segment_up','p_segment'])
                a,b,c=st.columns(3);a.metric('Saved stage snapshots',len(history));b.metric('Official results',len(official));c.metric('Final direction accuracy',f'{((official.p_up>=.5)==(official.winner=="UP")).mean():.1%}' if len(official) else 'Pending')
                summary=[]
                for i in range(3):
                    r=segment[segment.stage==i]
                    summary.append({'Stage':f'{i*5}–{(i+1)*5}m','Resolved spot-proxy forecasts':len(r),'Accuracy':f'{((r.p_segment>=.5)==(r.segment_up==1)).mean():.1%}' if len(r) else 'Pending'})
                st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)
                if len(official):
                    st.metric('Brier score (lower is better)',f'{((official.p_up-(official.winner=="UP").astype(int))**2).mean():.3f}')
                    pl=sum((1 if ('UP' if r.p_up>=.5 else 'DOWN')==r.winner else 0)-(r.up_ask if r.p_up>=.5 else r.down_ask) for _,r in official.iterrows())
                    st.metric('Hypothetical one-share P/L before costs',f'${pl:+.2f}')
                st.dataframe(history.head(40),hide_index=True,use_container_width=True)
                st.download_button('Export saved accuracy history',history.to_csv(index=False),'btc_accuracy_history.csv','text/csv')
            else:st.write('No predictions saved yet. Leave the app running to begin collecting snapshots.')
            st.caption('Local SQLite file persists across restarts. Stage results use Kraken 1-minute spot closes, NOT Chainlink. Official results require an explicit resolved winner from Polymarket; otherwise pending. Paper returns exclude fees and slippage. No orders placed.')
            con.close()
        except (sqlite3.Error,OSError) as exc:st.error(f'History database error: {exc}')

    st.markdown('**04 · Historical observation log** · Record observations for later testing; no trades are placed.')
    if 'logs' not in st.session_state:st.session_state.logs=[]
    if st.button('Record current observation'):
        st.session_state.logs.append({'utc':datetime.now(timezone.utc).isoformat(),'slug':slug,'spot_proxy':price,'strike':strike if strike>0 else None,'strike_source':reference_source,'seconds_remaining':remaining,'rsi14':rs,'ema9':ema9,'ema21':ema21,'volatility_1m':minute_vol,'up_ask':asks.get('up'),'down_ask':asks.get('down'),'model_up_probability':p_up if strike>0 else None})
        st.success('Observation added to this session.')
    if st.session_state.logs:
        st.dataframe(pd.DataFrame(st.session_state.logs),use_container_width=True)
        st.download_button('Download observations CSV',pd.DataFrame(st.session_state.logs).to_csv(index=False),'btc_signal_observations.csv','text/csv')
    st.caption('The countdown updates live; other data refreshes when you reload the page. Session observations may disappear if the server restarts; download the CSV. No API keys are used.')

    st.divider()
    st.markdown('**UTC market window details**')
    st.markdown(f'**Current UTC window:** {datetime.fromtimestamp(start,timezone.utc):%Y-%m-%d %H:%M}–{datetime.fromtimestamp(start+900,timezone.utc):%H:%M} • **Time remaining:** {remaining//60}m {remaining%60}s')
    st.markdown(f'[Open current Polymarket window](https://polymarket.com/event/{slug})')
