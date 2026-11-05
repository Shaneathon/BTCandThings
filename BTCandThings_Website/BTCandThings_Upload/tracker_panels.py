"""Shared tracker presentation and asset-local research estimates. No writes."""
from datetime import datetime, timezone
from html import escape
import json
import math


def research_signal(frame, now, end, target=None):
    """BTC-style momentum and zero-drift baseline, never a Champion model.

Only completed, contiguous minute observations are accepted. Probabilities
compare the selected asset's spot proxy to its target, not official settlement.
"""
    from market_candles import rsi14
    if len(frame) < 50:
        return {'ready': False, 'reason': 'At least 50 completed one-minute candles are required.'}
    history = frame.tail(120)
    times = [t.timestamp() for t in history['time']]
    age = now - (times[-1] + 60)
    if not 0 <= age < 120:
        return {'ready': False, 'reason': 'Price feed is stale or ahead of the observation time.'}
    if any(b-a != 60 for a, b in zip(times, times[1:])):
        return {'ready': False, 'reason': 'Recent one-minute candle history has gaps.'}
    if end <= now:
        return {'ready': False, 'reason': 'This market window has closed. Refresh market data.'}
    close = history['close'].astype(float)
    if not all(math.isfinite(v) and v > 0 for v in close):
        return {'ready': False, 'reason': 'Price history contains invalid values.'}
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    rsi = rsi14(close)
    change = float(close.iloc[-1]/close.iloc[-4]-1)
    spread = float(ema9.iloc[-1]-ema21.iloc[-1])
    slope = float(ema9.iloc[-1]-ema9.iloc[-4])
    rsi_change = float(rsi.iloc[-1]-rsi.iloc[-4])
    sign = lambda v: 1 if v > 0 else -1 if v < 0 else 0
    score = sum(map(sign, (spread, slope, change, float(rsi.iloc[-1])-50, rsi_change)))
    direction = 'UP' if score >= 2 else 'DOWN' if score <= -2 else 'NEUTRAL'
    returns = [math.log(b/a) for a, b in zip(close, close.iloc[1:])]
    mean = sum(returns)/len(returns)
    volatility = math.sqrt(sum((r-mean)**2 for r in returns)/(len(returns)-1))
    probability = None
    if target is not None and math.isfinite(target) and target > 0:
        sigma = max(volatility, .00005)*math.sqrt(max((end-now)/60, 1))
        z = math.log(float(close.iloc[-1])/target)/sigma
        probability = min(.995, max(.005, .5*(1+math.erf(z/math.sqrt(2)))))
    return dict(ready=True, reason=None, direction=direction, score=score,
                swing=spread != 0 and change*spread < 0 and rsi_change*spread < 0,
                probability=probability, price=float(close.iloc[-1]), rsi=float(rsi.iloc[-1]),
                ema9=float(ema9.iloc[-1]), ema21=float(ema21.iloc[-1]),
                change3=change, source_time=times[-1]+60)


def signal_card(heading, direction, detail):
    color, arrow = {'UP': ('up', '↗'), 'DOWN': ('down', '↘')}.get(direction, ('neutral', '→'))
    return (f'<div class="signal-card {color}"><div class="card-heading">{escape(heading)}</div>'
            f'<div class="card-value signal-{color}">{escape(direction)} {arrow}</div>'
            f'<div class="card-meta">{escape(detail)}</div></div>')


def countdown_html(asset, duration, start, end, now, target, verified, listed=True):
    """Fixed selected window; never roll a stale target into the next market.

Anchor elapsed time to server observation + monotonic browser time, avoiding
client wall-clock skew. A closed window stays closed until a data refresh.
"""
    label = f'POLYMARKET US · {asset} {duration} WINDOW'
    value = 'PENDING' if target is None else f'${target:,.5f}' if asset == 'XRP' else f'${target:,.2f}'
    source = 'OFFICIAL TARGET VERIFIED' if verified else 'SCHEDULED WINDOW · CONTRACT UNVERIFIED'
    if not listed:
        source = 'NO LISTED MARKET · RESEARCH CHART ONLY'
    window = f'{datetime.fromtimestamp(start, timezone.utc):%H:%M}–{datetime.fromtimestamp(end, timezone.utc):%H:%M} UTC'
    config = json.dumps(dict(start=start, end=end, observed=now, segments=5, listed=listed))
    return '''<!doctype html><html><head><style>
    *{box-sizing:border-box}body{margin:0;background:transparent;color:#edf4ff;font-family:system-ui,sans-serif}
    .panel{background:linear-gradient(110deg,#17263c,#121e30);border:1px solid #334b66;border-radius:14px;padding:22px;min-height:348px;display:flex;flex-direction:column;justify-content:space-between}
    .top{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap}.label{font-size:11px;letter-spacing:1.2px;color:#9dafc8;font-weight:700}
    .time{font-size:clamp(38px,5vw,65px);font-variant-numeric:tabular-nums;font-weight:800}.price{font-size:25px;color:#38bdf8;font-weight:800}
    .meta{font-size:12px;color:#9dafc8;margin-top:8px}.track{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:18px}.seg{height:5px;border-radius:6px;background:#2c3c52;overflow:hidden}.fill{height:100%;background:#ffc36a;width:0}
    </style></head><body><div class="panel"><div class="top"><div><div class="label">'''+escape(label)+'''</div><div class="time" id="timer">--:--</div></div>
    <div><div class="label">US PRICE TO BEAT</div><div class="price">'''+escape(value)+'''</div><div class="meta">'''+escape(source)+'''</div></div></div>
    <div><div id="stage" class="price" style="font-size:14px"></div><div class="meta">'''+escape(window)+'''</div>
    <div class="track">'''+''.join(f'<div class="seg"><div class="fill" id="f{i}"></div></div>' for i in range(5))+'''</div><div class="meta" id="elapsed"></div></div></div>
    <script>const cfg='''+config+''';const loaded=performance.now();
    function tick(){if(!cfg.listed){document.getElementById('timer').textContent='NOT LISTED';document.getElementById('stage').textContent='NO MARKET COUNTDOWN';return;}const now=cfg.observed+(performance.now()-loaded)/1000;
    const length=cfg.end-cfg.start,elapsed=Math.max(0,Math.min(length,now-cfg.start));
    const remain=Math.max(0,Math.ceil(cfg.end-now));const pad=n=>String(n).padStart(2,'0');
    document.getElementById('timer').textContent=pad(Math.floor(remain/60))+':'+pad(remain%60);
    document.getElementById('stage').textContent=remain===0?'WINDOW CLOSED · REFRESH MARKET DATA':'STAGE '+Math.min(5,Math.floor(elapsed/(length/5))+1)+' / 5 · '+Math.floor(Math.min(4,Math.floor(elapsed/(length/5)))*length/5/60)+'–'+Math.floor((Math.min(4,Math.floor(elapsed/(length/5)))+1)*length/5/60)+' MIN';
    for(let i=0;i<5;i++)document.getElementById('f'+i).style.width=(100*Math.max(0,Math.min(1,(elapsed-i*length/5)/(length/5))))+'%';
    document.getElementById('elapsed').textContent='Elapsed: '+Math.floor(elapsed/60)+'m '+Math.floor(elapsed%60)+'s';}
    tick();setInterval(tick,250);</script></body></html>'''
