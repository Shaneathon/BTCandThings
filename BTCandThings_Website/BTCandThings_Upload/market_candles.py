"""Common candles, indicators, and visualizations for all market workspaces.

Every feed is a labeled *spot or futures proxy*, not an official Polymarket US
reference or settlement feed. No API secrets, trades, or DB writes are used.
"""
from datetime import datetime, timezone
from html import escape
import math
import os

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
        proxy=os.environ.get('BTC_METALS_PROXY_URL','').strip().rstrip('/')
        if proxy:
            if proxy not in ('http://127.0.0.1:8770','http://localhost:8770'):
                raise ValueError('Expected reviewed loopback metals source')
            raw=get_json(proxy+'/candles',{'asset':asset})
            symbol={'GOLD':'XAU/USD','SILVER':'XAG/USD'}.get(asset)
            if (raw.get('asset')!=asset or raw.get('currency')!='USD' or raw.get('source_symbol')!=symbol
                    or raw.get('is_official_settlement_feed') is not False):
                raise ValueError('Metals proxy identity/currency unverified')
            columns=['time','open','high','low','close','volume']
            frame=pd.DataFrame(raw.get('candles',[]),columns=columns)
            frame['time']=pd.to_datetime(frame['time'],unit='s',utc=True)
            return clean_ohlc(frame,now),'Gold-API sampled '+symbol+' quote proxy (NOT official Chainlink; sampled candles)'
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
