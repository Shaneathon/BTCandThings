"""Compact 6-asset × 5m/15m market workspace.

The existing BTC 15m research model stays on its original page. All other
routes show independently verified US contract metadata and optional spot
charts. Never infer official settlement or trading probabilities from spot.
"""
from datetime import datetime, timezone
import html
import math

import pandas as pd

from market_board import typed_reference

ASSETS = {
    "BTC": {"name": "Bitcoin", "slug": "btc", "symbols": ("btc", "xbt"), "pair": "XBTUSD"},
    "ETH": {"name": "Ethereum", "slug": "eth", "symbols": ("eth",), "pair": "ETHUSD"},
    "XRP": {"name": "XRP", "slug": "xrp", "symbols": ("xrp",), "pair": "XRPUSD"},
    "SOL": {"name": "Solana", "slug": "sol", "symbols": ("sol",), "pair": "SOLUSD"},
    "GOLD": {"name": "Gold", "slug": "gold", "symbols": ("gold", "xau"), "pair": None},
    "SILVER": {"name": "Silver", "slug": "silver", "symbols": ("silver", "xag"), "pair": None},
}
DURATIONS = {"5m": 300, "15m": 900}
# As listed on the Polymarket US Crypto/Commodities pages Nov 5, 2026.
# We do not construct an unsupported gold/silver 5m event as though it exists.
LISTED_DURATIONS = {
    "BTC": ("5m", "15m"), "ETH": ("5m", "15m"),
    "XRP": ("5m", "15m"), "SOL": ("5m", "15m"),
    "GOLD": ("15m",), "SILVER": ("15m",)
}


def event_slug(asset, duration, start):
    if asset not in ASSETS or duration not in DURATIONS:
        raise ValueError("Unknown asset or duration")
    if duration not in LISTED_DURATIONS[asset]:
        return None
    dt = datetime.fromtimestamp(start, timezone.utc)
    return f"{ASSETS[asset]['slug']}-updown-{duration}-{dt:%Y-%m-%d-%H%M}z"


def window_for(now, duration):
    seconds = DURATIONS[duration]
    start = int(now) // seconds * seconds
    return start, start + seconds


def verified_target(market, asset, start, duration):
    return typed_reference(market, ASSETS[asset]["symbols"], start, DURATIONS[duration])


def price_label(asset, value):
    if value is None:
        return "PENDING"
    digits = 5 if asset == "XRP" else 3 if asset == "SILVER" else 2
    return f"${value:,.{digits}f}"


def load_spot_candles(get_json, pair):
    """Kraken *spot proxy*, never the official CF Benchmarks settlement index."""
    raw = get_json("https://api.kraken.com/0/public/OHLC", {"pair": pair, "interval": 1})
    if raw.get("error"):
        raise ValueError("Kraken returned an error")
    result = raw.get("result", {})
    key = next(k for k in result if k != "last")
    candles = result[key]
    frame = pd.DataFrame(candles, columns=["time","open","high","low","close","vwap","volume","count"])
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.iloc[:-1].dropna(subset=["close"]).tail(120)


def render_workspace(st, components, asset, duration, now, discover, full_market, get_json):
    """Only renders the selected market. All API failures fail closed."""
    start, end = window_for(now, duration)
    item = ASSETS[asset]
    st.markdown(f"## {item['name']} · {duration} market")
    st.caption("Polymarket US · UTC-aligned market windows · research-only monitor")
    if duration not in LISTED_DURATIONS[asset]:
        st.info(f"Polymarket US does not currently list a {duration} Up/Down market for {item['name']}. "
                "This view is reserved for future availability. No contract, quote or forecast is fabricated.")
        st.markdown("[Browse Polymarket US Crypto & Commodities](https://polymarket.us/hub/crypto-commodities)")
        return

    slug = event_slug(asset, duration, start)
    contract = None
    target = None
    state = "Unverified"
    diagnostics = []
    try:
        event, found, diagnostics = discover(slug)
        if found and found.get("slug"):
            contract_slug = str(found["slug"])
            market = full_market(contract_slug)
            if isinstance(market, dict) and market.get("slug") == contract_slug:
                target = verified_target(market, asset, start, duration)
                state = "Verified target" if target is not None else "Contract found · target pending"
                contract = market
            else:
                state = "Contract details unverified"
        elif event:
            state = "Event found · contract mapping pending"
        else:
            state = "Market discovery pending"
    except Exception as exc:
        state = "API temporarily unavailable"
        diagnostics.append(type(exc).__name__)

    a, b, c, d = st.columns(4, gap="small")
    a.metric("Price to beat · official US", price_label(asset, target))
    b.metric("Market duration", duration)
    c.metric("Time remaining", f"{(end-int(now))//60:02d}:{(end-int(now))%60:02d}")
    d.metric("Contract", "Verified" if contract else "Pending")
    # Browser-side countdown updates without needing a Streamlit rerun.
    components.html(
        "<div style='background:#151f32;border:1px solid #29384e;border-radius:12px;"
        "padding:12px 18px;color:#e2e8f0;font:600 15px system-ui'>"
        "<span style='color:#94a3b8;font-weight:400'>Market closes in </span>"
        "<span id='remaining'>--:--</span></div>"
        "<script>const e=" + str(end*1000) + ";function tick(){const s=Math.max(0,Math.ceil((e-Date.now())/1000));"
        "document.getElementById('remaining').textContent="
        "String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}"
        "tick();setInterval(tick,1000);</script>", height=57)

    st.caption(f"Market window: {datetime.fromtimestamp(start,timezone.utc):%H:%M}–"
               f"{datetime.fromtimestamp(end,timezone.utc):%H:%M} UTC · {state}")
    st.markdown(f"[View selected market on Polymarket US](https://polymarket.us/event/{slug})")

    if item["pair"]:
        st.markdown("#### Spot price trend")
        try:
            frame = load_spot_candles(get_json, item["pair"])
            if frame.empty:
                st.info("Completed spot candles are not available yet.")
            else:
                st.metric(f"Kraken {asset}/USD spot proxy", price_label(asset, float(frame['close'].iloc[-1])))
                st.line_chart(frame.set_index("time")["close"].rename(f"{asset} spot"), height=220)
                st.caption("Completed Kraken 1-minute candles, not the official Polymarket settlement index. "
                           "This chart is observational and does not produce a trading prediction.")
        except Exception as exc:
            st.info(f"Spot chart unavailable ({type(exc).__name__}). Official market verification is unaffected.")
    else:
        st.info("Gold and Silver use different settlement feeds. No unofficial spot chart is substituted for the official reference.")

    x, y = st.columns(2)
    with x:
        st.markdown("#### Prediction")
        st.info("Not yet validated for this asset and duration. No BTC-only model output is reused.")
    with y:
        st.markdown("#### Performance")
        st.info("Independent historical accuracy and paper-trade results pending dedicated collection.")
    with st.expander("Market verification details", expanded=False):
        st.write(f"Event: {slug}")
        st.write(f"Verification: {state}")
        if diagnostics:
            st.caption("Discovery notes: " + "; ".join(str(d)[:130] for d in diagnostics[:4]))
