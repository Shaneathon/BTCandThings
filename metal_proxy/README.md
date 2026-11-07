# Gold/silver sampled quote proxy

The user verified api.gold-api.com returns GOLD/XAU and SILVER/XAG USD quotes
with recent `updatedAt` timestamps. Exact settlement records separately identify
Chainlink XAU/USD-Streams-ForexPrice (2 decimals) and XAG/USD-Streams-ForexPrice
(3 decimals), with equality resolving UP. This proxy is **not Chainlink** and
is not asserted to replicate the settlement index or its license/access rights.

The service samples two public quote URLs about every 20 seconds total cycle,
validates symbol/currency, finite positive price, timezone and source freshness,
and persists genuine source observations. Duplicate timestamps are deduplicated;
conflicting values for a source timestamp are rejected. 429 responses honor
Retry-After or a 15-minute cooldown. No keys, purchases or trading endpoints.
Provider access terms and long-term availability have not been independently
verified; no public redistribution endpoint is introduced by this installer.

Closed one-minute bars require at least two distinct updates spanning 30 seconds.
They are sampled quote OHLC, **not full-market tick-derived OHLC**, and have no
invented volume. Missing minutes are never filled. Only the latest contiguous
suffix is returned, capped at 120 bars. Initial research warm-up needs 50
completed contiguous minutes; gaps, stale updates or closures can make it longer.
Do not backfill synthetic history to make the collector report READY sooner.

The private loopback API binds 127.0.0.1:8770 and contains only public quote
data/provenance. The separate DynamicUser service has a persistent state cache,
10% CPU and 96 MiB memory limits. Official targets, contract identity checks and
verified Chainlink settlements remain unchanged. Research candles carry explicit
source_name/source_symbol and `is_official_settlement_feed=false` into Supabase.

`deploy/install-metals-proxy.sh --prepare` tests sampler source only. `--apply`
also prepares/tests a new research release while the old one runs, starts the
sampler, checks its API, then changes the research reader's environment and
briefly restarts only btc-multiasset-research. Failed immediate research startup
restores its prior unit. Existing Champion/Challenger and paper services are not
restarted. Old persisted Yahoo rate-limit cooldowns can expire naturally during
warm-up. Existing maintenance units are updated without stopping applications
so this cache is backed up and the sampler's service health is monitored.

PBot's existing per-market research wallets can consume resulting fresh forecasts
automatically, under their existing paper-entry rules. They remain hypothetical
fixed-price experiments; this change does not validate quotes, liquidity or
realistic profitability. Gold/silver may remain paused when no current official
market/target exists even after proxy warm-up. Real trading remains disabled.

This installs the collector data path. A separately hosted tracker does not gain
access to a droplet's loopback API automatically: its deployment/data-source
connection must be checked separately. No new public proxy route or website
deployment is performed by this script.
