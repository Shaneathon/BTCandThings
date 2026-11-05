# BTCandThings, PBot, CBot and Coinbase tracker handoff

Repository: Shaneathon/BTCandThings. Current preparation branch:
`tracker/coinbase-research`.

| App | Target | Source | Scope |
| --- | --- | --- | --- |
| BTCandThings | btc.shaneathon.com | BTCandThings_Website/BTCandThings_Upload | Existing ten-market tracker |
| PBot | pbot.shaneathon.com | trading_bot | Polymarket ten-stream paper bot |
| CBot | cbot.shaneathon.com | coinbase_bot | Coinbase BTC/ETH/XRP/SOL USD spot paper bot |
| Coinbase tracker | coin.shaneathon.com | coinbase_tracker | Public research data and read-only CBot feed |

The user requested the Coinbase tracker look like the Polymarket tracker in
design, using its own Coinbase data for all four coins. No expiry countdown or
price-to-beat should be copied into spot trading.

The user changed the former tbot hostname to **pbot**. Do not provision the old
hostname. CBot's `.com` suffix is assumed from the user's existing domain.
The two bots and Coinbase tracker have separate database paths, service identities, read tokens,
status/API ports and dashboard ports. Common utility code does not share wallets.

Existing DigitalOcean path: /root/BTCandThings. Preserve btc-collector.service
(Pixel Champion) and btc-challenger.service. No new Challenger models are needed
for the other nine Polymarket streams. Focus on core collected data first.

Already live: uniform BTCandThings tracker UI on GitHub main. Data/settlement/cloud
preparation remains on research/ten-stream-setup; this combined bot branch
inherits it and adds the two bot apps. No new bot was deployed, no hostname/DNS or
TLS was configured, no production database was changed and no real trade was sent.

Read next:

- deploy/CONNECT_WHEN_READY.md — ten-market collector and Supabase integration.
- trading_bot/README.md and trading_bot/CONNECT_WHEN_READY.md — PBot data gates,
  persistent virtual portfolio, risk limits and independent hosting.
- coinbase_tracker/README.md and DATA_CATALOG.md — four-coin research scope,
  BTC-style design with continuous spot semantics, data quality, storage and
  read-only CBot input. No orders, account credentials or bot wallets.
- coinbase_bot/README.md — Coinbase public data, independent spot paper strategy,
  cost assumptions, limitations and live broker development still required.

Live trading is an eventual user goal, not authorization to place an order now.
Both submission implementations are unavailable. Do not claim that a paper
backend is a production-ready live broker. Do not connect personal keys, deploy
untested services or change existing production data while preparing locally.

Remaining connection work: actual source/schema/quote validation, server capacity
and identities/read permissions, Supabase schema/credentials, paper-only service
activation, new hosting/DNS/TLS and live website checks. Current environment API
requests remain denied by the enforced network policy; saved domain drafts are
not applied policy. No new secrets have been supplied.

Resume phrase:

> I'm ready to connect BTCandThings, the Coinbase tracker, PBot and CBot. Continue
> from tracker/coinbase-research and BOT_HANDOFF.md. Keep existing services running,
> use the separate pbot/cbot hostnames, and keep real trading disabled.

The new Coinbase tracker code is prepared, not deployed. Its public REST archive
does not capture every tick or L2 update. Account fee tiers/private fills,
Coinbase-specific cloud upload and historical backfill are not connected.
