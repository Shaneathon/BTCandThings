# Collection upgrades and all-market paper rollout

This is a deployment plan, not a claim that the additional feeds are installed.
Preserve btc-collector, btc-challenger, btc-multiasset-research, Coin and both
paper bots. New collectors should be isolated, resource-budgeted services.

Prepared implementation: `deploy/expand-pbot-markets.sh --apply` adds the
independent hypothetical research slots, and `deploy/install-market-capture.sh
--apply` installs the isolated unauthenticated Coinbase raw recorder. Both have
passed local preparation/rehearsal checks but require actual droplet output to
confirm deployment and live subscription availability. The recorder is not yet
a normalized, sequence-validated order book and does not feed fills.

## Market coverage

| Venue / stream | Current source coverage | Next paper state |
| --- | --- | --- |
| BTC/ETH/XRP/SOL, Polymarket US 5m and 15m | Crypto proxy candles, typed market metadata, research forecasts; some verified outcomes and partial raw quotes | Directional sandbox where fresh inputs exist; executable-fill mode blocked until mapped quotes are verified |
| Gold/silver, Polymarket US 15m | Typed metadata/quotes sometimes available; price feed rate-limited/unavailable | Provision visibly paused slots; never fabricate predictions or replace gold with a gold token |
| BTC-USD/ETH-USD/XRP-USD/SOL-USD, Coinbase | Completed 1m candles, public metadata, sampled trades/books, paper decision journal | Existing CBot paper logic already covers all four; increase source continuity before judging high-frequency strategies |

Champion/Challenger B predictions exist for BTC 15m only. For the additional
Polymarket streams, use the separately labeled generic research baseline,
not a claimed Champion or a cloned Bitcoin prediction. Keep the original two
Bitcoin ledgers/configurations unchanged. Additional per-market directional
wallets are experiments, not a single funded portfolio; report the distinction.

## Tier 1: execution and data integrity

1. **Polymarket full books.** Capture the exact verified contract's book and BBO
   with source and receive timestamps, currency, side/size fields and market
   state. Preserve raw records and parse version. Missing sides remain missing.
   Validate whether a size field counts levels, shares or another unit before
   using it. The observed `askDepth`/`bidDepth` must not be assumed to be shares.
2. **Direction mapping evidence.** Record reviewed contract semantics and explicit
   mapping, evidence source/version and validity window. Preserve index symbols,
   rounding and tie rules. Neither array position nor an unlabelled 0/1 result
   establishes UP/DOWN. Reject contradictory evidence and changed contracts.
3. **Coinbase streams.** Add public heartbeat, trades and Level-2 subscriptions
   when confirmed supported without trading credentials. Archive raw messages,
   product identity, exchange timestamp, receipt timestamp, channel and sequence
   fields. Verify channel-specific sequence semantics; do not impose a generic
   global sequence rule. Rebuild books on snapshot/reconnect, deduplicate trades,
   detect loss and mark coverage gaps. No stale book is tradable during repair.
4. **REST repair, not constant hammering.** Keep the existing completed candles
   and metadata as fallback. Pace requests, honor Retry-After, jitter reconnects,
   and share a rate budget by host. WebSocket availability does not make REST
   data unnecessary. Some US streams need authenticated access; verify read-only
   scopes/terms before configuration, without enabling the order path.
5. **Audit timestamps.** Retain publication/receipt/feature-cutoff/decision/order-
   arrival times separately. Store a monotonic clock for durations and track
   wall-clock offset. Backdated candle boundaries are not availability evidence.
6. **Fees and market rules.** Store product increments, minimum/maximum size,
   tick size, trading-disabled state, fee parameters and provenance. Maintain
   conservative scenario costs until a real applicable fee tier is verified.

## Tier 2: settlement and context

- Official index observations if accessible under appropriate terms: source
  index, sample time, received time, quality/revision flag, averaging progress.
  Validate with settled official prices; do not label exchange spot as the index.
- Basis among Coinbase, Kraken and official index, including asynchronous-source
  age. Do not interpolate future prices backwards into a contemporaneous basis.
- Reliable metals data with explicit instrument identity. Futures GC/SI, XAU/XAG
  spot, tokens and official settlement indices are different instruments. A
  futures/spot proxy can be separately studied but not silently substituted.
- Scheduled macro announcements with original release time and revisions; event
  tags should not expose a later revised value to an earlier decision.
- Derivatives context and sentiment only after source semantics, cost, coverage,
  publication timestamps and incremental out-of-sample usefulness are established.

## Data contract

At minimum each record needs:

`venue, product_or_contract_id, event_id, asset, duration, channel, source_time,
received_at, recorded_at, sequence_or_trade_id, payload_version, raw_payload,
quality_status, quality_reason, collector_version`.

Derived features also need a feature cutoff, input versions/IDs and strategy
version. Portfolio decisions need an experiment ID, model ID, parameter hash,
market opportunity ID, quote/reference-price basis, decision reason and latency
assumption. Paper positions must explicitly identify synthetic versus observed-
quote fills. Never log authorization headers, private keys or account secrets.

## Resource and storage plan

The droplet has roughly 2 GiB RAM and about 44 GiB free disk in the latest
reported checks. Four-product full-depth/tick data can grow far faster than
one-minute candles. Measure bytes/hour before choosing retention; there is no
credible fixed days-of-history estimate without that measurement.

- Use one shared collector per venue, not one WebSocket per strategy.
- Append raw events to rotated/compressed segments; keep a compact hot database
  of current books, normalized trades, candles, features and manifests.
- Store durable segment hashes and verified-upload manifests before deleting
  local raw data. Off-server object storage requires a chosen account/bucket and
  cost/permission configuration; do not silently activate a paid service.
- Batch summaries to existing Supabase tables only after additive schema review;
  do not stream every Level-2 event into the current prediction tables.
- Keep research collectors' checkpoints, databases and credentials independent
  from legacy Champion. Use consistent SQLite backup/export rather than copying
  a WAL database file while it is being written.
- Apply disk high-water stops, bounded queues/backpressure, reconnect limits,
  failed-upload alarms and explicit gap markers. Never silently drop events.
- Collect service health, bytes/hour, feed freshness, gap count, REST 429s,
  reconnect count, upload backlog and clock offset alongside market data.

## Deployment order with minimum manual work

1. Preserve the running paper baselines and review their first recorded entries.
2. Prepare all ten Polymarket directional experiment slots using existing
   research snapshots; start only those with fresh verified metadata/signals.
   Gold/silver remain paused until their feeds recover or a valid source is added.
3. Add a separate venue-data recorder and health/quality report. Test on the
   droplet once; use its results to confirm actual WebSocket shapes and limits.
4. Once quote mapping is established, run separate observed-quote paper ledgers
   alongside the fixed-price experiments. Do not replace or merge their history.
5. Add replay/latency/depth models and evaluate candidate strategies on new data.
6. Set up daily automated review reports and experiment version tracking; actual
   autonomous strategy switching needs a tested controller and promotion rules.

The user has already authorized paper-only changes. Production/live trading
is still disabled. DNS and portal protection are unrelated to order execution.
