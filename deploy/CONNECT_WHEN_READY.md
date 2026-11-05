# Connection handoff — BTCandThings ten-market research system

## Say this in chat when ready

> I'm ready to connect the 10-market collector to DigitalOcean and Supabase.
> Continue from research/ten-stream-setup and deploy/CONNECT_WHEN_READY.md.
> Keep btc-collector.service and btc-challenger.service running, preserve Champion,
> use the shortest tested setup flow, and do not place real trades.

No passwords or keys belong in that message.

## Scope and preserved decisions

- Website: btc.shaneathon.com, repository Shaneathon/BTCandThings.
- Ten streams: BTC/ETH/XRP/SOL × 5m/15m, GOLD/SILVER × 15m.
- Existing production path: /root/BTCandThings.
- Champion: btc-collector.service, Pixel V13.5. Challenger: btc-challenger.service.
- Separate new unit: btc-multiasset-research.service. No existing service is edited.
- Prepared branch: research/ten-stream-setup. This branch is not merged into main.
- Five 3m stages in 15m windows, five 1m stages in 5m windows. No metals 5m markets
  are invented. The already-published uniform tracker update remains unchanged
  while this branch is prepared.

## What is prepared and tested locally

1. Ten-stream source collection with shared candles, exact market/asset/window
   identity checks, observed-time snapshots, durable SQLite storage, capacity
   preflight and pause on critically low free disk.
2. Exact-contract raw BBO capture using the pinned polymarket-us 2.4.1 SDK route.
   Bid/ask evidence is not yet mapped to UP/DOWN execution fills.
3. Settlement queue rotation revisits long-pending markets and accepts only
   explicit semantic UP/DOWN winners on final, matching full-contract records.
   Numeric settlement values and conflicting/unknown outcomes remain pending.
4. Opt-in uploads to only asset_market_windows, asset_proxy_candles and
   asset_market_predictions, with natural keys and durable retry checkpoints.
   Market final states cannot be overwritten with pending states. Target/window
   or winner conflicts are reported rather than overwritten.
5. Read-only website performance wiring, per asset and duration, using the most
   recent up to 20 verified markets, complete cohort pagination, and one first
   valid prediction per model/market. No BTC scores are reused in other markets.
6. Offline paper accounting requiring reviewed, timely executable quotes and
   explicit fees/slippage. Missing final outcomes or side mappings skip trades.
   This is not a capital-constrained portfolio simulator or liquidity model.
7. One-block installer, a validation script, a private cloud-config wizard and
   research-only stop script. No filled credential files are present in Git.

The end-to-end fixture test covers all ten market streams through collection,
explicit settlement, fake Supabase synchronization and simulation accounting.
It is a synthetic test, not actual performance evidence.

## Remaining checks that need the connected environment

- Actual DigitalOcean capacity and connectivity. Capacity gate requires 1 GiB
  free disk and 256 MiB available memory before installation. Runtime pauses
  new collection below 100 MiB free disk. Retention/backups must be agreed before
  extended unattended operation; no automatic deletion is enabled.
- Live Polymarket typed terms and official settlement fields across every stream.
  SDK source confirms the BBO route and numeric settlement shape, but does not
  document semantic UP/DOWN mapping for every asset. Live response evidence and
  official terms must support any adapter expansion; do not infer mappings.
- Gold/silver proxy freshness, closures and rate limits. Yahoo futures feeds are
  explicitly proxies, not the official Chainlink settlement source.
- Review schema and role model in staging. db/proposed_multi_asset_schema.sql is
  additive and preserves btc_* tables; it has not been executed here. The optional
  db/research_access_policies.sql is an unexecuted draft for scoped JWT roles;
  key-only synchronization does not implement scoped-user token refresh. An
  approved server-only Supabase credential may bypass RLS and must stay private.
- Confirm staging writes, restart/retry behavior and read-only dashboard access
  against a real Supabase instance before enabling production synchronization.
  HTTP fixtures do not prove PostgreSQL constraints, RLS or credential permissions.
- Confirm executable quote-side mappings and actual fee schedules before enabling
  automatic paper fills. No live order path exists in this package.

Current session evidence: no supplied Supabase/DigitalOcean credentials, no custom
network domains enforced, and live market calls denied by the environment proxy.
No production database writes or DigitalOcean deployments were performed.

## Minimal planned connection sequence

1. Inspect the running units/capacity read-only and validate real API response
   evidence from the droplet. Resolve source/settlement ambiguities before
   promising full ten-stream simulation readiness.
2. Review/apply the additive research schema once in Supabase, validate staging
   access, then provision the approved private server credential.
3. Use the one installation block from deploy/README.md, changing --start to
   --start-cloud for permanent synchronization. The private wizard asks for URL
   and a hidden server key in the console, checks research-table READ access,
   and exclusively creates root-mode-600 /etc/btcandthings-research.env. It never
   prints the key and never overwrites an existing configuration.
4. Wait for the first full pass, then use the printed single validation command.
   Check all streams, quote capture, cloud sync errors/backlog and verified
   settlement counts separately. A PID or collection_ready alone is not full
   simulation readiness. No fresh redeploy of existing collectors is needed.
5. Publish the prepared website history wiring only after schema/read access is
   validated. The current site keeps working while the separate collector is
   installed. Check the live website after publication.

The installer refuses activation if any of the ten current streams lacks a valid
market/target or sufficient fresh candles. If a metals market is closed, resolve
its expected-hours readiness policy explicitly rather than bypassing checks or
reporting success for only eight streams.
