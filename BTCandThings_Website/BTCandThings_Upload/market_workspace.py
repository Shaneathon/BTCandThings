"""Uniform 6-asset × 5m/15m market workspace.

The existing BTC 15m research model stays on its original page. All other
routes show independently verified US contract metadata and asset-local
spot research estimates. Never label those as verified settlement probabilities.
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


def render_workspace(st, components, asset, duration, now, discover, full_market, get_json, history_loader=None):
    """BTC-style layout with strictly asset/window-local data; no archive writes."""
    from market_candles import load_candles, resample_complete, candle_svg
    from tracker_panels import research_signal, signal_card, countdown_html
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
            if event and event.get("slug") != slug:
                status = "Event identity mismatch"
            elif found and found.get("slug"):
                details = full_market(str(found["slug"]))
                if isinstance(details, dict) and details.get("slug") == str(found["slug"]):
                    target = verified_target(details, asset, start, duration)
                    if target is not None:
                        contract = details
                    status = "Target verified" if target is not None else "Asset / window / target pending"
                else:
                    status = "Contract unverified"
            else:
                status = "Contract mapping pending" if event else "Event not verified"
        except Exception as exc:
            status = f"API unavailable ({type(exc).__name__})"

    st.markdown(f"### {item['name']} · {duration} tracker")
    st.caption("Polymarket US · asset-specific market and signals · UTC windows")
    if not available:
        st.warning(f"{item['name']} {duration} is not currently listed. No market or target is assumed.")
    frame = pd.DataFrame()
    feed_name, feed_error = "Feed not connected", None
    try:
        frame, feed_name = load_candles(get_json, asset, item["pair"], now)
    except Exception as exc:
        feed_error = type(exc).__name__
    signal = research_signal(frame, now, end, target)
    ready = signal['ready'] and available
    direction = signal.get('direction', 'PENDING') if ready else 'PENDING'
    spot = float(frame['close'].iloc[-1]) if not frame.empty else None

    st.html("""<style>
    .st-key-workspace_candlestick_panel{background:linear-gradient(110deg,#17263c,#121e30);border:1px solid #334b66;border-radius:14px;padding:10px 14px 8px;height:348px;box-sizing:border-box;overflow:hidden}
    </style>""")
    left, right = st.columns([1, 1], gap="medium")
    with left:
        components.html(countdown_html(asset, duration, start, end, now, target,
                                       contract is not None, listed=available), height=358, scrolling=False)
    with right:
        with st.container(key="workspace_candlestick_panel"):
            heading, selector = st.columns([2, 1], vertical_alignment="center")
            with heading:
                st.markdown(f"**{asset} / USD · completed candles**")
            with selector:
                interval = st.radio("Candle interval", ("1m", "5m"), horizontal=True,
                                    label_visibility="collapsed", key=f"candles_{asset}_{duration}")
            chart = resample_complete(frame, interval, now) if not frame.empty else frame
            if chart.empty:
                st.info("Waiting for complete candles. Other panels remain available.")
            else:
                components.html(candle_svg(chart, asset, interval, target), height=245, scrolling=False)
            st.caption(feed_name)
    if slug:
        st.markdown(f"[Open {asset} {duration} on Polymarket US](https://polymarket.us/event/{slug}) · {status}")
    if feed_error:
        st.warning(f"{asset} candle feed unavailable ({feed_error}). Research signals paused.")
    elif not signal['ready']:
        st.caption(signal['reason'])

    lean_col, preflight_col = st.columns([1, 1], gap="medium")
    with lean_col:
        lean, position = st.columns(2, gap="medium")
        with lean:
            detail = (f"Directional agreement: {abs(signal['score'])}/5 · Swing watch: "
                      + ("WATCH · potential reversal" if signal['swing'] else "CLEAR")) if ready else "Fresh, contiguous asset-specific candles required."
            st.html(signal_card(f"CURRENT {asset} {duration} MOMENTUM LEAN", direction, detail))
        with position:
            st.html(signal_card("POSITION SUGGESTION · RESEARCH MODE", "WAIT / OBSERVE",
                                f"{asset} {duration} · {status}. No validated trading edge yet."))
        st.caption(f"{asset} {duration} · proxy momentum from {feed_name}. "
                   "This uses recent one-minute candles; the same asset can have the same momentum "
                   "in its 5m and 15m views. Contract forecasts use each window’s own target and expiry.")
        if ready:
            observed = datetime.fromtimestamp(signal['source_time'], timezone.utc)
            st.caption(f"Signal candle closed {observed:%Y-%m-%d %H:%M:%S} UTC · "
                       f"{asset} spot {price_label(asset, signal['price'])} · "
                       f"RSI {signal['rsi']:.1f} · 3m change {signal['change3']:+.3%}")
        st.caption(f"Selected market: {slug or 'not listed'} · {status}")
    preflight = ready and 0 < end-now <= min(180, DURATIONS[duration])
    with preflight_col:
        st.html(signal_card(f"NEXT {asset} {duration} WINDOW PREFLIGHT", direction if preflight else "PENDING",
                            f"Experimental {asset} opening lean · {abs(signal['score'])}/5 agreement" if preflight
                            else "Preflight begins with 3 minutes remaining in this market."))
        st.caption("Next-window proxy direction context, not a prediction of its contract winner.")
    advice = (f"WATCH {direction} CAUTIOUSLY · reversal risk flagged." if signal.get('swing') else
              f"WATCH {direction} · experimental momentum only.") if preflight and direction != 'NEUTRAL' else "WAIT / OBSERVE · continue monitoring the current market."
    st.html('<div class="preflight-advice"><strong>◉ PREFLIGHT SUGGESTION</strong> &nbsp; '+html.escape(advice)+'</div>')

    st.markdown('#### Final Target Forecast · Research')
    probability = signal.get('probability') if ready and target is not None else None
    if probability is None:
        st.info("Forecast paused until this asset's official target and fresh completed candles are available.")
    else:
        above, below, gap = st.columns(3)
        above.metric('Forecast: finish ABOVE target', f'{probability:.1%}')
        below.metric('Forecast: finish BELOW target', f'{1-probability:.1%}')
        gap.metric(f'{asset} proxy − official target', f'{spot-target:+,.5f}')
        st.progress(float(probability), text=f'ABOVE {probability:.1%} | BELOW {1-probability:.1%}')
        st.info(f"Baseline research estimate · {asset} candles only. Historical calibration is not connected.")
        st.caption("Zero-drift lognormal spot model, not a validated probability of official Polymarket settlement. "
                   "The spot and official reference feeds differ; this does not establish a betting edge.")
    trade_tab, performance_tab, advanced_tab = st.tabs(["Trading", "Performance", "Advanced · Research & Diagnostics"])
    with trade_tab:
        st.markdown('### Trade opportunity advisor')
        st.html(signal_card("RESEARCH STATUS", "WAIT / OBSERVE", "No executable-price model or real orders are connected."))
        prices = st.columns(3)
        prices[0].metric('Official price to beat', price_label(asset, target))
        prices[1].metric('Proxy last close', price_label(asset, spot))
        prices[2].metric('Market status', status)
    with performance_tab:
        history = None
        if history_loader:
            try:
                history = history_loader(asset, duration)
            except Exception as exc:
                st.caption(f"Cloud history temporarily unavailable ({type(exc).__name__}).")
        if history and history.get('models'):
            for model, score in history['models'].items():
                st.markdown(f"**{model}**")
                stats = st.columns(3)
                stats[0].metric('Verified win rate', f"{score['accuracy']:.1%}")
                stats[1].metric('Scored markets', score['markets'])
                stats[2].metric('Brier score', f"{score['brier']:.4f}")
            st.caption(history['cohort'])
            st.caption('Models may have different market coverage. These are descriptive scores, not a paired promotion test or calibration.')
        else:
            st.metric('Verified win rate', 'PENDING')
            st.caption(f"Independent settled {asset} {duration} history is not available yet. Bitcoin results are never reused here.")
        st.caption("History is read-only. Collection and cloud synchronization run separately on the server.")
    with advanced_tab:
        st.write(f"**Asset / duration:** {asset} / {duration}")
        st.write(f"**Official target:** {'Verified' if contract else 'Pending'}")
        st.write(f"**Completed proxy candles:** {len(frame)}")
        st.write(f"**Proxy feed:** {feed_name}")
        st.write(f"**Signal status:** {'Fresh' if ready else 'Paused'}")
        if ready:
            st.caption(f"RSI(14): {signal['rsi']:.1f} · EMA9: {signal['ema9']:.5f} · "
                       f"EMA21: {signal['ema21']:.5f} · 3m move: {signal['change3']:+.2%}")
            st.caption(f"Latest completed candle close: {datetime.fromtimestamp(signal['source_time'], timezone.utc):%Y-%m-%d %H:%M:%S} UTC")
        if slug:
            st.write(f"**Event slug:** {slug}")
        if diagnostics:
            st.caption("Discovery notes: " + "; ".join(str(d)[:130] for d in diagnostics[:4]))
        if not frame.empty:
            st.download_button("Export completed proxy candles CSV", frame.to_csv(index=False).encode('utf-8'),
                               file_name=f"{asset.lower()}_{duration}_proxy_candles.csv", mime='text/csv',
                               key=f"proxy_export_{asset}_{duration}")
        st.caption("Research only. No orders placed. No permanent archive or cloud writes from this workspace.")
