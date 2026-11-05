"""Six verified Polymarket US 15-minute asset routes; read-only market radar.

A URL/slug is a navigation target, not proof of a live contract or a verified
price. Show the official price-to-beat only from matching typed API metadata.
Never reuse BTC's price, indicators, or predictions for other assets.
"""
from datetime import datetime, timezone
import math

ASSETS = (
    ("BTC", "Bitcoin", "btc", ("btc", "xbt")),
    ("ETH", "Ethereum", "eth", ("eth",)),
    ("XRP", "XRP", "xrp", ("xrp",)),
    ("SOL", "Solana", "sol", ("sol",)),
    ("GOLD", "Gold", "gold", ("gold", "xau")),
    ("SILVER", "Silver", "silver", ("silver", "xag")),
)


def market_slug(prefix, start):
    """Polymarket US 15m event slug pattern, grounded in official event pages."""
    return f"{prefix}-updown-15m-{datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d-%H%M}z"


def typed_reference(market, allowed_symbols, start):
    """Only accept a target tied to the expected asset, type and 15m window."""
    if not isinstance(market, dict):
        return None
    terms = market.get("assetPriceTerms")
    if not isinstance(terms, dict):
        return None
    asset = terms.get("asset")
    if not isinstance(asset, dict):
        return None
    if str(asset.get("symbol", "")).lower() not in allowed_symbols:
        return None
    kind = str(terms.get("marketType", "")).upper()
    if "UPDOWN" not in kind and "UP_DOWN" not in kind:
        return None
    def epoch(value):
        try:
            return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
        except (ValueError, TypeError, OverflowError):
            return None
    if epoch(terms.get("windowStart")) != start or epoch(terms.get("windowEnd")) != start+900:
        return None
    raw = terms.get("priceToBeat")
    if not isinstance(raw, dict) or str(raw.get("currency", "USD")).upper() != "USD":
        return None
    try:
        value = float(raw.get("value"))
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def format_price(asset, price):
    if price is None:
        return "PENDING"
    return f"${price:,.5f}" if asset == "XRP" else (
        f"${price:,.3f}" if asset == "SILVER" else f"${price:,.2f}")


def render_market_radar(st, discover, get_market, start):
    """Independent read-only panel; failure in one asset cannot stop BTC app."""
    st.markdown("### Six-asset market radar · 15-minute windows")
    st.caption("BTC, ETH, XRP, SOL, Gold and Silver · Polymarket US only. "
               "This is a market/target monitor, not six independently validated prediction models.")
    for base in (0, 3):
        cols = st.columns(3, gap="small")
        for col, (ticker, name, prefix, allowed) in zip(cols, ASSETS[base:base+3]):
            slug = market_slug(prefix, start)
            with col:
                with st.container(border=True):
                    st.markdown(f"**{name} · {ticker}**")
                    try:
                        event, contract, _ = discover(slug)
                        if not event and not contract:
                            st.caption("US contract not confirmed for this window")
                            target = None
                        elif not contract or not contract.get("slug"):
                            st.caption("Event found · contract mapping pending")
                            target = None
                        else:
                            details = get_market(str(contract["slug"]))
                            if not isinstance(details, dict) or details.get("slug") != contract["slug"]:
                                target = None
                                st.caption("Contract details unverified")
                            else:
                                target = typed_reference(details, allowed, start)
                                st.caption("Official target verified" if target is not None
                                           else "Official target / asset metadata pending")
                        st.metric("Price to beat (US)", format_price(ticker, target))
                    except Exception as exc:
                        st.metric("Price to beat (US)", "PENDING")
                        st.caption(f"Market API unavailable ({type(exc).__name__})")
                    st.markdown(f"[Open {ticker} market on Polymarket US](https://polymarket.us/event/{slug})")
    st.caption("Different settlement feeds apply: crypto uses CF Benchmarks indices; "
               "Gold/Silver use Chainlink. A Kraken price is not an official market settlement. "
               "Existing BTC charts and predictions below remain BTC-only; "
               "additional asset collectors and models are not yet deployed.")
