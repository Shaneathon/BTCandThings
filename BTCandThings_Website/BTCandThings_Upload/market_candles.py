"""Common candles, indicators, and visualizations for all market workspaces.

Every feed is a labeled *spot or futures proxy*, not an official Polymarket US
reference or settlement feed. No API secrets, trades, or DB writes are used.
"""
from datetime import datetime, timezone
from html import escape
import math

import pandas as pd

KRAKEN = "https://api.kraken.com/0/public/OHLC"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
METAL_FUTURES = {"GOLD": "GC=F", "SILVER": "SI=F"}


def clean_ohlc(frame, now):
    """Normalize and retain only completed 1m bars; reject invalid prices."""
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    for key in ("open", "high", "low", "close", "volume"):
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
    frame = frame.dropna(subset=["time", "open", "high", "low", "close"])
    prices = frame[["open", "high", "low", "close"]]
    frame = frame[((prices > 0) & (prices < float("inf"))).all(axis=1)]
    frame = frame[(frame["high"] >= frame[["open", "close", "low"]].max(axis=1)) &
                  (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))]
    cutoff = pd.Timestamp.fromtimestamp(now - 60, tz="UTC")
    frame = frame[frame["time"] <= cutoff]
    return frame.drop_duplicates(subset=["time"]).sort_values("time").tail(300).reset_index(drop=True)


def load_candles(get_json, asset, pair, now):
    """Return completed 1m OHLCV and an explicit source/quality label."""
    if pair:
        raw = get_json(KRAKEN, {"pair": pair, "interval": 1})
        if raw.get("error"):
            raise ValueError("Kraken reported an error")
        result = raw.get("result") or {}
        key = next((key for key in result if key != "last"), None)
        if key is None:
            raise ValueError("Kraken candles unavailable")
        records = result[key]
        frame = pd.DataFrame(records, columns=[
            "time", "open", "high", "low", "close", "vwap", "volume", "count"])
        frame["time"] = pd.to_datetime(pd.to_numeric(frame["time"]), unit="s", utc=True)
        label = "Kraken crypto spot proxy (not official US settlement)"
    else:
        symbol = METAL_FUTURES.get(asset)
        if symbol is None:
            raise ValueError("No configured market-data proxy")
        # Yahoo Finance chart data may be delayed, rate-limited or unavailable.
        # Futures quotes are NOT spot Gold/Silver or the official Chainlink feed.
        raw = get_json(YAHOO + symbol.replace("=", "%3D"),
                       {"interval": "1m", "range": "1d"})
        chart = (raw.get("chart") or {}).get("result") or []
        if not chart:
            raise ValueError("Futures proxy unavailable")
        result = chart[0]
        times = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [])
        if not quotes:
            raise ValueError("Futures proxy has no OHLC values")
        quote = quotes[0]
        frame = pd.DataFrame({"time": pd.to_datetime(times, unit="s", utc=True),
                              "open": quote.get("open"), "high": quote.get("high"),
                              "low": quote.get("low"), "close": quote.get("close"),
                              "volume": quote.get("volume")})
        label = f"{symbol} futures proxy (Yahoo Finance; NOT official Chainlink reference)"
    frame = clean_ohlc(frame, now)
    return frame, label


def resample_complete(frame, interval, now):
    """1m or fully completed 5m bars, never a partial 5m aggregate."""
    if interval == "1m":
        return frame.copy()
    if interval != "5m":
        raise ValueError("Unsupported candle interval")
    if frame.empty:
        return frame.copy()
    candles = (frame.set_index("time").resample("5min").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).dropna(subset=["open", "close"]))
    cutoff = pd.Timestamp.fromtimestamp(now, tz="UTC")
    candles = candles[candles.index + pd.Timedelta(minutes=5) <= cutoff]
    # Only include 5m bars with five 1m observations.
    counts = frame.set_index("time")["close"].resample("5min").count()
    candles = candles[counts.reindex(candles.index).fillna(0) >= 5]
    return candles.reset_index()


def rsi14(close):
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    value = 100 - 100 / (1 + up / down.replace(0, float("nan")))
    value = value.mask((down == 0) & (up > 0), 100)
    value = value.mask((up == 0) & (down > 0), 0)
    return value.mask((up == 0) & (down == 0), 50)


def indicators(frame, now):
    """Five transparent votes from completed bars; not a trained forecast."""
    if len(frame) < 30:
        return None
    age = now - (int(frame["time"].iloc[-1].timestamp()) + 60)
    if age < -1 or age > 180:
        return {"stale": True, "age_seconds": age}
    close = frame["close"].astype(float)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    rsi = float(rsi14(close).iloc[-1])
    price = float(close.iloc[-1])
    if not math.isfinite(rsi):
        return None
    momentum3 = price / float(close.iloc[-4]) - 1
    momentum5 = price / float(close.iloc[-6]) - 1
    votes = [
        (1 if ema9.iloc[-1] > ema21.iloc[-1] else -1),
        (1 if price > ema9.iloc[-1] else -1),
        (1 if rsi > 52 else -1 if rsi < 48 else 0),
        (1 if momentum3 > 0 else -1 if momentum3 < 0 else 0),
        (1 if momentum5 > 0 else -1 if momentum5 < 0 else 0),
    ]
    score = sum(votes)
    direction = "UP" if score >= 2 else "DOWN" if score <= -2 else "NEUTRAL"
    return {"stale": False, "price": price, "ema9": float(ema9.iloc[-1]),
            "ema21": float(ema21.iloc[-1]), "rsi": rsi,
            "momentum3": momentum3, "momentum5": momentum5,
            "score": score, "direction": direction, "agreement": sum(abs(v) for v in votes),
            "age_seconds": age}


def candle_svg(frame, asset, interval, reference=None):
    """Compact SVG candlestick chart with axes and optional official target line."""
    if frame.empty:
        return ""
    data = frame.tail(64).reset_index(drop=True)
    W, H = 900, 290
    left, right, top, bottom = 18, 82, 18, 34
    plot_w, plot_h = W-left-right, H-top-bottom
    prices = list(data["high"].astype(float)) + list(data["low"].astype(float))
    if reference is not None and math.isfinite(reference):
        prices.append(float(reference))
    lo, hi = min(prices), max(prices)
    pad = max((hi-lo)*0.08, max(hi, 1)*0.00001)
    lo -= pad
    hi += pad
    y = lambda v: top + (hi-v)/(hi-lo)*plot_h
    step = plot_w / len(data)
    width = max(2, step*0.58)
    shapes = [f'<rect width="{W}" height="{H}" fill="#101a2b" rx="10"/>']
    for i in range(5):
        value = lo + (hi-lo)*i/4
        yy = y(value)
        shapes.append(f'<line x1="{left}" x2="{W-right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#283b52" stroke-width="1"/>')
        shapes.append(f'<text x="{W-right+8}" y="{yy+4:.1f}" fill="#9cb0c7" font-size="11">{value:,.5f}</text>')
    for i, row in data.iterrows():
        x = left+(i+0.5)*step
        o, h, l, c = (float(row[k]) for k in ("open","high","low","close"))
        color = "#34d399" if c >= o else "#fb7185"
        shapes.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y(h):.2f}" y2="{y(l):.2f}" stroke="{color}" stroke-width="1.4"/>')
        top_body = min(y(o),y(c))
        body_h = max(1.5, abs(y(o)-y(c)))
        shapes.append(f'<rect x="{x-width/2:.2f}" y="{top_body:.2f}" width="{width:.2f}" height="{body_h:.2f}" fill="{color}" rx="1"/>')
    if reference is not None and math.isfinite(reference):
        yy = y(reference)
        shapes.append(f'<line x1="{left}" x2="{W-right}" y1="{yy:.2f}" y2="{yy:.2f}" stroke="#fbbf24" stroke-width="1.6" stroke-dasharray="7 5"/>')
        shapes.append(f'<text x="{left+8}" y="{max(12, yy-7):.2f}" fill="#fbbf24" font-size="11">OFFICIAL TARGET</text>')
    for index in sorted(set([0, len(data)//2, len(data)-1])):
        stamp = data.iloc[index]["time"].strftime("%H:%M")
        shapes.append(f'<text x="{left+(index+.5)*step:.1f}" y="{H-10}" text-anchor="middle" fill="#9cb0c7" font-size="11">{stamp} UTC</text>')
    title = escape(f"{asset} / USD · {interval} completed candles")
    shapes.append(f'<text x="{left+8}" y="13" fill="#e2e8f0" font-size="11">{title}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{title}">' + "".join(shapes) + "</svg>"


def render_candles(components, frame, asset, interval, reference=None):
    svg = candle_svg(frame, asset, interval, reference)
    if svg:
        components.html('<div style="margin:0;background:#101a2b;border-radius:12px;">'+svg+'</div>',
                        height=315, scrolling=False)


def stage_progress(st, duration, now, start, end):
    """Displays elapsed stage only, never a future directional forecast."""
    if duration == "15m":
        stages = [("Opening",0,300),("Middle",300,600),("Final",600,900)]
    else:
        stages = [("Opening",0,60),("Middle",60,180),("Final",180,300)]
    elapsed = max(0, min(end-start, now-start))
    cols = st.columns(3)
    for col, (name, begin, finish) in zip(cols, stages):
        with col:
            progress = max(0, min(1, (elapsed-begin)/(finish-begin)))
            st.caption(f"{name} · {begin//60}–{finish//60} min")
            st.progress(progress)


def streaming_candles_html(frame, asset, interval, reference=None):
    """Browser-only Kraken v2 OHLC stream; never changes completed model bars."""
    import json
    symbols={'BTC':'BTC/USD','ETH':'ETH/USD','XRP':'XRP/USD','SOL':'SOL/USD'}
    if asset not in symbols or interval not in ('1m','5m'):
        raise ValueError('Unsupported streaming chart instrument or interval')
    source=frame.reset_index() if 'time' not in frame.columns else frame
    seed=[]
    for row in source.tail(120).itertuples(index=False):
        stamp=pd.Timestamp(row.time)
        if stamp.tzinfo is None: raise ValueError('Chart seed timestamps require timezone')
        values={key:float(getattr(row,key)) for key in ('open','high','low','close')}
        if (not all(math.isfinite(v) and v>0 for v in values.values()) or
                values['high']<max(values.values()) or values['low']>min(values.values())): continue
        seed.append(dict(time=int(stamp.timestamp()),**values))
    target=float(reference) if reference is not None else None
    if target is not None and (not math.isfinite(target) or target<=0): target=None
    cfg=json.dumps(dict(symbol=symbols[asset],interval=int(interval[:-1]),seed=seed,target=target),allow_nan=False).replace('</','<\\/')
    return '''<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;background:#151f32;color:#b6c6da;font:11px system-ui}#chart{height:210px}
    .status{display:flex;justify-content:space-between;gap:8px;padding:3px 5px;min-height:17px}.status a{color:#819ab9}
    #feed{color:#fbbf24}#price{color:#e8efff;font-variant-numeric:tabular-nums}
    </style></head><body><div class="status"><span id="feed" role="status">Loading streaming chart…</span><span id="price"></span></div>
    <div id="chart"></div><div class="status"><span>Kraken spot · forming candle included · Central time</span><a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">Charts by TradingView</a></div>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const cfg=__CONFIG__,feed=document.getElementById('feed'),price=document.getElementById('price');
    const central=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'});
    function state(text,color='#fbbf24'){feed.textContent=text;feed.style.color=color;}
    if(!window.LightweightCharts){state('Chart library unavailable — refresh or check content blockers.','#f87171');}
    else{
      const host=document.getElementById('chart');
      const chart=LightweightCharts.createChart(host,{width:host.clientWidth,height:210,
        layout:{background:{type:'solid',color:'#151f32'},textColor:'#a9bdd4',fontSize:10},
        grid:{vertLines:{color:'#213148'},horzLines:{color:'#213148'}},
        rightPriceScale:{borderColor:'#33445c'},timeScale:{borderColor:'#33445c',timeVisible:true,secondsVisible:false,
          tickMarkFormatter:t=>central.format(new Date(t*1000)).replace(/:\\d{2} (AM|PM)/,' $1')},
        localization:{timeFormatter:t=>central.format(new Date(t*1000))},handleScroll:true,handleScale:true});
      const series=chart.addCandlestickSeries({upColor:'#22c55e',downColor:'#f87171',borderVisible:false,
        wickUpColor:'#22c55e',wickDownColor:'#f87171',priceFormat:{type:'price',precision:cfg.symbol==='XRP/USD'?5:2,minMove:cfg.symbol==='XRP/USD'?.00001:.01}});
      const bars=new Map(cfg.seed.map(b=>[b.time,b]));
      series.setData([...bars.values()].sort((a,b)=>a.time-b.time));chart.timeScale().fitContent();
      if(cfg.target!==null)series.createPriceLine({price:cfg.target,color:'#fbbf24',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'US target'});
      new ResizeObserver(()=>chart.applyOptions({width:host.clientWidth})).observe(host);
      let ws=null,retry=null,stopped=false,backoff=1000,lastData=0;
      function connect(){
        if(stopped||document.hidden)return;
        state('Connecting to Kraken '+cfg.symbol+'…');
        ws=new WebSocket('wss://ws.kraken.com/v2');
        ws.onopen=()=>{
          backoff=1000;lastData=0;state('Connected · waiting for candle data');
          ws.send(JSON.stringify({method:'subscribe',params:{channel:'ohlc',symbol:[cfg.symbol],interval:cfg.interval,snapshot:true}}));
        };
        ws.onmessage=event=>{
          let msg;try{msg=JSON.parse(event.data);}catch{return;}
          if(msg.method==='subscribe'&&msg.success===false){state('Kraken subscription unavailable','#f87171');return;}
          if(msg.channel!=='ohlc'||!Array.isArray(msg.data))return;
          let accepted=false;
          for(const row of msg.data){
            if(row.symbol!==cfg.symbol||Number(row.interval)!==cfg.interval)continue;
            const t=Date.parse(row.interval_begin)/1000;
            const bar={time:t,open:Number(row.open),high:Number(row.high),low:Number(row.low),close:Number(row.close)};
            if(!Number.isFinite(t)||t%(cfg.interval*60)!==0||t>Date.now()/1000+120||
              ![bar.open,bar.high,bar.low,bar.close].every(x=>Number.isFinite(x)&&x>0)||
              bar.high<Math.max(bar.open,bar.close,bar.low)||bar.low>Math.min(bar.open,bar.close,bar.high))continue;
            bars.set(t,bar);accepted=true;
          }
          if(!accepted)return;
          const sorted=[...bars.values()].sort((a,b)=>a.time-b.time).slice(-300);
          bars.clear();for(const b of sorted)bars.set(b.time,b);
          series.setData(sorted);
          const latest=sorted[sorted.length-1];lastData=Date.now();
          price.textContent='$'+latest.close.toLocaleString('en-US',{maximumFractionDigits:cfg.symbol==='XRP/USD'?5:2});
          if(Date.now()/1000-latest.time>cfg.interval*60+120)state('Connected · latest candle is stale','#f87171');
          else state('STREAMING · received '+central.format(new Date(lastData)),'#67e8c0');
        };
        ws.onerror=()=>state('Stream connection error · retrying','#f87171');
        ws.onclose=()=>{
          if(stopped||document.hidden)return;
          state('Disconnected · reconnecting','#f87171');
          clearTimeout(retry);retry=setTimeout(connect,backoff);backoff=Math.min(backoff*2,30000);
        };
      }
      const watchdog=setInterval(()=>{
        if(ws&&ws.readyState===WebSocket.OPEN&&lastData&&Date.now()-lastData>45000)
          state('Connected · no new candle update for '+Math.floor((Date.now()-lastData)/1000)+'s','#fbbf24');
      },5000);
      document.addEventListener('visibilitychange',()=>{
        clearTimeout(retry);
        if(document.hidden){if(ws)ws.close();state('Chart paused while tab is hidden');}
        else if(!ws||ws.readyState===WebSocket.CLOSED)connect();
      });
      window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(retry);clearInterval(watchdog);if(ws)ws.close();});
      connect();
    }
    </script></body></html>'''.replace('__CONFIG__',cfg)
