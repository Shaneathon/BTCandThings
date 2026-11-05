# BTCandThings research collection

Start with [the connection handoff](../deploy/CONNECT_WHEN_READY.md) and
[installer instructions](../deploy/README.md). All collectors are independent of
the existing Champion and Challenger; no real trading code is present.

## Ten-stream workflow

Requires Python 3.10+ and pandas>=2.1,<3. Use an existing isolated checkout;
no worktree is needed. Store local state outside the repository:

```bash
python3 collection/ten_streams.py --db /tmp/research.sqlite
python3 collection/ten_streams.py --db /tmp/research.sqlite --loop
python3 collection/ten_streams.py --db /tmp/research.sqlite --validate
python3 -m unittest discover -s collection -v
```

Ten streams use six asset-specific shared feeds: BTC/ETH/XRP/SOL 5m+15m and
GOLD/SILVER 15m. Completed candles, typed Polymarket identities/targets, research
snapshots and raw BBO evidence are retained in SQLite. Times of observation and
source-candle closes remain separate. Kraken and Yahoo futures are labeled proxy
sources, never official settlement feeds. Missing/stale/gapped inputs pause the
affected stream instead of fabricating predictions.

Settlement reconciliation rotates through pending closed contracts and accepts
only explicit final semantic UP/DOWN winners with matching identity, window and
target. Numeric sides and ambiguous metadata stay pending. Current/recent-market
refresh cannot downgrade a locally verified final. Live semantic winner fields
still need confirmation; the pinned SDK's settlement endpoint only types a
numeric settlement value, which this collector does not guess a side from.

Raw BBO bestBid/bestAsk capture uses the SDK 2.4.1 documented public route and
requires the exact contract slug. It records `side_mapping_verified: false` until
an authoritative per-contract mapping is connected. It is excluded from automatic
paper fills and cloud quote upload.

### Opt-in cloud synchronization

Default collection makes no cloud writes. The optional service environment file
uses BTC_RESEARCH_SYNC_ENABLED=1 and private BTC_RESEARCH_SUPABASE_URL/KEY values.
The installer wizard creates it without displaying the key. Per-table access is
limited in code to asset_market_windows, asset_proxy_candles and
asset_market_predictions. No legacy btc_* tables or trade endpoints are accepted.

Sync sends naturally keyed rows, preserves immutable predictions, updates candle
corrections, and never overwrites a remote final with pending state. Verified
winner/identity/target conflicts fail rather than silently overwrite. Failed
requests receive no checkpoint and retry on the next pass. Batch success does
not imply an empty backlog; --validate --require-cloud checks both.

Standalone synchronization is an explicit write operation, only after staging
and production authorization:

```bash
python3 collection/cloud_sync.py --db /path/research.sqlite --apply
```

The environment must already contain the private credentials. Never put filled
.env files in Git or send their contents through chat. TLS verification and
inherited proxy settings remain enabled; credentialed redirects are refused.

### Offline simulation

```bash
python3 collection/simulation.py --db /path/research.sqlite \
  --quotes /path/reviewed-quotes.json --quantity 10 \
  --fee-per-share 0.01 --slippage-per-share 0.02 --out /tmp/simulation.json
```

Those costs are examples, not a verified fee schedule. Quotes must contain exact
market_slug/contract_slug, captured_at, source_name=Polymarket US,
side_mapping_verified=true, and up_ask/down_ask. Only use normalized quotes from a
reviewed adapter; raw BBO records intentionally do not qualify. Entry quotes must
arrive at or within 30 seconds after the prediction and before market close.
One earliest observed prediction per model/market is selected; no hindsight
selection. Final verified settlement and no future source information are
required. Missing inputs produce explicit skipped trades. Output is local,
exclusive-create JSON, not live trading, depth-aware execution or a capital ledger.

## Original four-crypto workflow

collector.py and audit.py remain separate standard-library tools for four crypto
15m streams. audit.py is not the validator for ten_streams.py. It provides
read-only local audits and schema-shaped exports, refuses overwriting an export,
and refuses invalid-record export. Use the ten-stream validator above for six
assets, raw quotes, cloud batch status and full stream coverage.

PR #8's separate scripts/collect_four_crypto.py was reviewed through Git and is
not modified/deployed here. No production database, service or trading action
has been taken. Live sources and real staging permissions remain external checks.
