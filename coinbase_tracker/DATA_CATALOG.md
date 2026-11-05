# Coinbase research data coverage

Scope: Coinbase Advanced public SPOT BTC-USD, ETH-USD, XRP-USD and SOL-USD.
Routes and schemas reviewed against official coinbase-advanced-py 1.8.4.
Live endpoint responses remain unverified in the current restricted environment.

| Data | Collection and storage | Interpretation |
| --- | --- | --- |
| Product identity, currency, type, trading restrictions | Public product record; validated and archived | No assumed aliases, leverage or foreign products |
| Size/price increments and minima, optional maxima | Product metadata, archived as returned | Actual account eligibility is separate |
| Price, 24h change/volume and other returned product fields | Full returned product metadata | Fields can be absent; no values invented |
| 1m OHLCV | Completed, aligned, finite, consistent bars; keyed by product/start | Most recent bounded response is fetched; gaps are reported |
| Corrections | Candle rows can update; raw source observations retained | Published features retain their first real observation time |
| Recent trades | Up to 100 per product/poll; immutable product/trade_id keys | Not complete tick capture; conflicts are rejected |
| Trade time, price, size, reported side | Typed product-matched print records | BUY/SELL preserved; no unsupported aggressor-side claim |
| Bid/ask and size | Product-matched, timestamp-checked book snapshots | Observed quotes, not guaranteed fills |
| Book depth | Requested 20 price levels per side | Not the full depth or sequence-based L2 reconstruction |
| Spread bps | (ask − bid) / mid × 10,000 | Current sampled book only |
| Base-unit depth and imbalance | Sum of sampled sizes; (bid size − ask size) / total | Same-asset book comparison, not a prediction |
| EMA9/21, 3m momentum | Completed 1m closes | Heuristic BUY/SELL/HOLD context, not a trade order |
| RSI14 | Simple 14-change gain/loss window | Explicit simple-window version, not Wilder smoothing |
| ATR14 | Mean of recent 14 true ranges | Simple-window price-unit estimate |
| 1m volatility | Sample SD of latest 20 log returns | Not annualized volatility or a risk guarantee |
| Candle VWAP approximation | Typical candle price × volume / total over available bars | Not trade-by-trade execution VWAP |
| 5m/15m change | Recent completed minute closes | Continuous spot movement, not expiring markets |
| Feature history | One first observed feature row per product/completed candle | No invented historical predictions or backdated records |
| Data quality | Component failures, gaps, freshness and request latency | A missing trade feed does not erase healthy candles/books |
| Source provenance | Public request URL/parameters, response, observation time and latency | No credentials or account endpoints |

All technical observation timestamps are UTC. Raw REST snapshots and sampled
trades do not guarantee capture of every order, cancellation or tick. Polling is
15 seconds by default, plus sequential request time; it is not high-frequency
streaming. No WebSocket sequencing/reconnect/backfill implementation is claimed.

Not connected: account balances, actual orders/fills, actual fee tier, account
permissions, transaction history, tax records, news/sentiment, on-chain flows,
exchange-wide cross-venue liquidity or derivative open interest/funding. Some
require authenticated read-only account access, licensed/external providers or
new collectors. They are not silently substituted with proxy estimates.

The raw archive is local SQLite. Supabase ingestion for this Coinbase-specific
schema, retention/backups, historical backfill and long-range cloud queries are
not implemented. Do not reuse Polymarket asset_market_windows tables for
continuous Coinbase markets. Source/server validation and storage sizing precede
extended unattended collection.
