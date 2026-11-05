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
    """Uniform candles + research panels; never substitute another asset's model."""
    from market_candles import (load_candles, resample_complete, indicators,
                                render_candles, stage_progress)
    start, end = window_for(now, duration)
    item = ASSETS[asset]
    available = duration in LISTED_DURATIONS[asset]
    slug = event_slug(asset, duration, start) if available else None
    target, contract = None, None
    diagnostics = []
    status = "Not listed" if not available else "Pending verification"

    if available:
        try:
            event, found, diagnostics = discover(slug)
            if found and found.get("slug"):
                details = full_market(str(found["slug"]))
                if isinstance(details, dict) and details.get("slug") == str(found["slug"]):
                    target = verified_target(details, asset, start, duration)
                    contract = details
                    status = "Target verified" if target is not None else "Target pending"
                else:
                    status = "Contract unverified"
            elif event:
                status = "Contract mapping pending"
            else:
                status = "Event not verified"
        except Exception as exc:
            status = f"API unavailable ({type(exc).__name__})"

    st.markdown(f"### {item['name']} · {duration} tracker")
    st.caption("Polymarket US · same tracker layout across assets · UTC market windows")
    if not available:
        st.warning(f"{item['name']} {duration} Up/Down is not currently listed on Polymarket US. "
                   "The chart and indicators below are research-only; no contract or price-to-beat is assumed.")

    # Price history is independent of contract discovery. Futures proxies for
    # metals are explicitly labeled and may be delayed/unavailable.
    frame = pd.DataFrame()
    feed_name = "Feed not connected"
    feed_error = None
    try:
        frame, feed_name = load_candles(get_json, asset, item["pair"], now)
        if frame.empty:
            feed_error = "No completed 1-minute candles returned"
    except Exception as exc:
        feed_error = f"{type(exc).__name__}: {str(exc)[:100]}"
    metrics = indicators(frame, now) if not frame.empty else None
    fresh = bool(metrics and not metrics.get("stale"))
    spot = float(frame["close"].iloc[-1]) if not frame.empty else None

    # The header and candlestick area share the BTC tracker dark-card style.
    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.markdown("#### Current market")
        m1, m2 = st.columns(2)
        m1.metric("Official price to beat", price_label(asset, target))
        m2.metric("Market status", status)
        m3, m4 = st.columns(2)
        m3.metric("Proxy last close", price_label(asset, spot))
        m4.metric("To target · proxy", (f"{spot-target:+,.5f}" if
                  target is not None and spot is not None else "PENDING"))
        st.caption("To-target compares separate feeds; it is NOT an official settlement margin.")
        components.html(
            "<div style='background:#151f32;border:1px solid #29384e;border-radius:12px;"
            "padding:12px 18px;color:#e2e8f0;font:600 18px system-ui'>"
            "<span style='color:#94a3b8;font-weight:400'>Market closes in </span>"
            "<span id='remaining'>--:--</span></div>"
            "<script>const e=" + str(end*1000) +
            ";function tick(){const s=Math.max(0,Math.ceil((e-Date.now())/1000));"
            "document.getElementById('remaining').textContent="
            "String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}"
            "tick();setInterval(tick,1000);</script>", height=64)
        st.caption(f"Window: {datetime.fromtimestamp(start,timezone.utc):%H:%M}–"
                   f"{datetime.fromtimestamp(end,timezone.utc):%H:%M} UTC")
        if slug:
            st.markdown(f"[Open this Polymarket US market](https://polymarket.us/event/{slug})")
        else:
            st.markdown("[Browse available Polymarket US markets](https://polymarket.us/hub/crypto-commodities)")

    with right:
        head, interval_col = st.columns([2, 1], vertical_alignment="center")
        with head:
            st.markdown("#### Candlestick chart")
        with interval_col:
            candle_interval = st.radio("Candle interval", ("1m", "5m"),
                                       horizontal=True, label_visibility="collapsed",
                                       key=f"candles_{asset}_{duration}")
        if not frame.empty:
            chart_frame = resample_complete(frame, candle_interval, now)
            if not chart_frame.empty:
                render_candles(components, chart_frame, asset, candle_interval, target)
            else:
                st.info("Waiting for complete candles at this interval.")
        else:
            st.info("Candle feed pending. Chart will appear automatically when the proxy feed is available.")
        st.caption(feed_name)
        if feed_error:
            st.caption("Data feed: " + feed_error[:150])
        if metrics and metrics.get("stale"):
            st.warning("Proxy feed is stale. Direction signals are disabled until fresh candles return.")
        st.caption("Green/red candles are completed proxy bars. Amber line is the separately verified US target, "
                   "when available. Crypto uses Kraken spot; metals use futures proxies, not official settlement feeds.")

    st.markdown("#### Market stages")
    stage_progress(st, duration, now, start, end)

    lean_col, preflight_col = st.columns(2, gap="medium")
    with lean_col:
        st.markdown("#### Current momentum lean")
        if fresh:
            st.metric("Experimental direction", metrics["direction"])
            st.caption(f"Agreement: {abs(metrics['score'])}/5 net votes · "
                       f"RSI(14): {metrics['rsi']:.1f} · "
                       f"3m move: {metrics['momentum3']:+.2%}")
            st.caption(f"EMA 9: {price_label(asset, metrics['ema9'])} · "
                       f"EMA 21: {price_label(asset, metrics['ema21'])}")
        else:
            st.metric("Experimental direction", "PENDING")
            st.caption("Requires at least 30 fresh completed 1-minute candles.")
        st.caption("Heuristic indicator agreement only; not a validated Polymarket prediction.")
    with preflight_col:
        st.markdown("#### Next-window preflight")
        st.metric("Forecast status", "RESEARCH ONLY" if fresh else "PENDING")
        if fresh:
            st.caption(f"Current trend context: {metrics['direction']} · "
                       f"5m proxy move: {metrics['momentum5']:+.2%}.")
        st.caption("A separately trained next-window forecast and its accuracy history are not connected yet.")

    end_col, perf_col = st.columns(2, gap="medium")
    with end_col:
        st.markdown("#### Final above/below target")
        st.metric("Validated probability", "PENDING")
        st.caption("Official target verification and independent model calibration are required. "
                   "No BTC-only probability is copied into this tracker.")
    with perf_col:
        st.markdown("#### Prediction performance")
        st.metric("Verified win rate", "PENDING")
        st.caption("One independent settled outcome per market; paper-trade P/L will require executable "
                   "quotes, fees, slippage and fills.")

    with st.expander("Data readiness and diagnostics", expanded=False):
        st.write(f"**Asset / duration:** {asset} / {duration}")
        st.write(f"**Market listing:** {'Listed' if available else 'Not currently listed'}")
        st.write(f"**Official US target:** {'Verified' if target is not None else 'Pending'}")
        st.write(f"**Completed proxy candles:** {len(frame)}")
        st.write(f"**Proxy feed:** {feed_name}")
        st.write(f"**Signal freshness:** {'Fresh' if fresh else 'Stale / insufficient'}")
        st.write("**Independent forecast / settlement archive:** Not connected")
        st.write("**Paper trading:** Not connected; no orders placed")
        if slug:
            st.write(f"**Event slug:** {slug}")
        if diagnostics:
            st.caption("Discovery notes: " + "; ".join(str(d)[:130] for d in diagnostics[:4]))
