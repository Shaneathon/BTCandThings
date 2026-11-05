# Coin — independent Coinbase research tracker

Target: **coin.shaneathon.com**. Four coins: **BTC, ETH, XRP, SOL**, each using its
own Coinbase USD spot product. The UI follows the Polymarket tracker's visual
language: dark masthead, asset selector, market cards and chart side-by-side,
directional cards, metrics and diagnostics. Market semantics stay Coinbase-specific:
continuous spot markets, no price-to-beat, expiry countdown or binary payoff.

The tracker is separate from btc.shaneathon.com, PBot and CBot wallets. It collects
public market data and offers read-only research data; it cannot place orders.
See [DATA_CATALOG.md](DATA_CATALOG.md) for precise coverage and omissions.

## Implemented

- Independent archival of product rules/status, completed one-minute OHLCV,
  product-matched depth books and sampled recent trades.
- Persistent deduplicated candles/trades; conflicting trade IDs cannot silently
  overwrite history. Raw responses include request and timing provenance.
- First-observed feature snapshots, indicators, spread/depth/imbalance and
  per-component health. Partial outages preserve independently healthy sources.
- 1m/5m/15m completed candlestick views, Coinbase bid/ask cards, momentum and CBot
  data readiness panels; tabs for overview, liquidity, prints, export and quality.
- Read-only authenticated status API. Explicit source/mode checks prevent bot
  wallet payloads from being mistaken for tracker data. No signing keys needed.
- Optional CBot --tracker-url reader so it can reuse this validated feed rather
  than duplicate market requests. CBot's separate risk engine still makes every
  decision and validates freshness; tracker readiness does not authorize trading.
- Separate identities/ports/templates and protected database identity checks.
  An accidental bot-ledger path is rejected before tracker schema writes.

## Local commands

From the existing repository root (no additional worktree required):

```bash
python3 -m unittest discover -s coinbase_tracker/tests -v
# Install coinbase_tracker/requirements.txt for UI development:
python3 coinbase_tracker/smoke_ui.py
streamlit run coinbase_tracker/app.py
```

The app initially shows SETUP. It does not fabricate market values or collect in
the browser. A separate public-data collector is required for continuous history:

```bash
python3 -m coinbase_tracker.collector --db /path/coin-research.sqlite --loop --interval 15
python3 -m coinbase_tracker.collector --db /path/coin-research.sqlite --status
```

The read-only status command fails on stale or incomplete readiness. Independent
component failures and candle quality are reported separately. REST interval is
at least five seconds; outages and sequential HTTP latency can extend a cycle.
Below 100 MiB free disk, new writes pause; no automatic deletion is performed.
Measure archive growth and choose backups/retention before extended collection.

## CBot integration

After private read-only API configuration, CBot can use:

```bash
python3 -m coinbase_bot.runner --ledger /path/cbot-paper.sqlite \
  --config coinbase_bot/paper.example.json --kill-file /path/CBOT_STOP \
  --tracker-url https://YOUR_PRIVATE_DATA_HOST/status --loop
```

The bot server supplies COIN_READ_TOKEN privately. Do not put it on a command
line, in the browser or in chat. This source token is distinct from CBot's own
status token. On one host, the private loopback status endpoint is supported.
Stale/foreign tracker reports are refused and missing components pause only the
affected bot input. Quotes remain subject to CBot's own freshness/size checks.

## Deployment preparation and external requirements

Prepared templates in deploy/ use a dedicated coin user, /opt/coin and
/var/lib/coin, API 8767 and UI 8504. Include the shared coinbase_bot/trading_bot
read-only data/transport modules when packaging this repository. No services,
users, database, DNS record or certificate have been installed here.

DNS/TLS for coin.shaneathon.com need the actual hosting endpoint/account. Review
capacity across all existing/new services; do not assume the current droplet
can host every UI. A separate Streamlit host can use the private HTTPS data API.
Keep existing collector services and BTC/PBot/CBot routes unchanged.

Actual public Coinbase API calls are currently denied by the environment's
network policy. api.coinbase.com is present in the saved configuration draft,
not applied policy. SDK/schema and fixture tests do not prove live availability.
No exchange credentials, real trading or private account endpoints are used.
Coinbase-specific cloud upload, full tick/L2 streaming, historical backfill and
read-only account-data integration remain future work.

## Validation

Nine tracker tests pass, covering all four source archives, restart/deduplication,
partial outages, incorrect books, gaps, conflicting trades, no foreign-wallet
writes, real observation timestamps and the read-only feed into CBot. Three
Streamlit fixture scenarios cover setup, independent asset selection with
1m/5m/15m charts and data outage. Existing PBot/CBot tests also run for shared
transport/reader changes. Tests contain synthetic data, not trading results.

## Resume

> Continue from tracker/coinbase-research and BOT_HANDOFF.md. Connect
> coin.shaneathon.com for BTC/ETH/XRP/SOL research data, feed CBot read-only,
> preserve the existing tracker and both bots, and keep real trading disabled.
