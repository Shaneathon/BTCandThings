# BTCandThings, PBot, CBot and Coinbase tracker handoff

Repository: Shaneathon/BTCandThings. Current preparation branch:
`tracker/coinbase-research`.

## Current confirmed status — November 6, 2026

This section supersedes historical preparation notes below. Last server evidence:
2026-11-06 23:47:54 UTC (5:47 PM Central). Do not infer current runtime health
forever from this timestamp; recheck before deploying or reporting live status.

- btc.shaneathon.com, coin.shaneathon.com, pbot.shaneathon.com and
  cbot.shaneathon.com have HTTPS and user visual confirmation.
- bets.shaneathon.com works; it is hosted separately on OpenAI Sites/Cloudflare,
  with code accessible from its original ChatGPT app conversation, not this repo.
- shaneathon.com portal works with server-side password protection. Username
  is Shaneathon; password is private and never belongs in chat/Git. Portal
  protection does not restrict direct access to individual dashboards.
- All 14 monitored services were active in the latest health output. Original
  btc-collector and btc-challenger remained running and Champion unchanged.
- PBot preserves Champion/B BTC15m control ledgers and has ten additional
  independent research wallets. Eight crypto streams monitor fresh predictions;
  GOLD_15m and SILVER_15m are paused. ALL Polymarket entries currently use
  hypothetical 50c reference prices plus assumed costs, not executable fills.
- CBot runs paper-only on BTC/ETH/XRP/SOL USD spot products using Coin's feed.
  It uses sampled bid/ask prices and assumed fees/slippage, not actual orders.
- Independent Coinbase raw recorder is capturing public trades/heartbeats;
  Level-2 disconnected in the probe (1006), is excluded, and is not fixed.
- DigitalOcean automated daily backups were enabled by user and confirmed in
  screenshot. First completed provider backup is not yet evidenced.
- Maintenance deployment is confirmed: seven server tests passed, first local
  set successfully backed up and integrity-checked **18 databases** at
  23:47:52 UTC. No backup failure recorded. Hourly SQLite snapshots, daily
  Supabase public-data exports and five-minute health timers are enabled.
- First cloud export was still pending in latest output; completion needs a
  follow-up check. That was the only warning. Gold/silver were paused notices.
- Root disk had 40.46 GiB free and memory 954 MiB available in that output.
- Private health report: https://shaneathon.com/health.html. Alerts are local
  journal/report only; no email/SMS/webhook notifications are configured.
- **Real trading is disabled and not authorized.** User authorizes autonomous
  versioned paper experiments, but a self-optimizing promotion controller has
  not been implemented. Keep baselines frozen and never rewrite results.

Next checks: first cloud export completion; first completed DigitalOcean backup.
Remaining development: verified Polymarket mapping/quote-realistic fills, metals
feeds, validated Level-2/replay, autonomous experiment review/promotion, optional
external notifications, full restore rehearsal. Betting Lab accordion change
must be confirmed in its original app conversation. Keep manual steps minimal.

## Historical November 6 implementation notes (superseded above)

Coin and PBot are deployed on the user's DigitalOcean droplet, with HTTPS
health checks and visual confirmation. PBot was observation-only. BTC Champion,
Challenger, multiasset research and Coinbase collectors remain running.
The Bitcoin audit found Challenger B promising near expiry on 95 matched
markets; Champion production calculations have not been changed.

Immediate priority: start two independent forward **paper-only** portfolios,
Champion V13.5 versus Challenger B. User explicitly authorizes paper experiment
tweaks without approval each time. Preserve a frozen baseline, version changes,
and don't label every loss an entry mistake. No real trading is authorized.
`deploy/start-pbot-sandbox.sh` prepares/installs a **hypothetical directional**
experiment with fixed 50c reference prices and explicit assumed costs; it does
not solve verified quote-side mapping or enable realistic executable fills.
Deployment still requires the user to run the published command on the droplet.

After the paper comparison, continue CBot and Betting Lab; the user requested a
server-side password-protected portal at shaneathon.com after those projects.
Only the portal needs password protection; direct dashboard access stays as is.
Expanded continuous market data/context collection was added last. Minimize
manual steps. Never stop existing collectors or expose credentials.

CBot installation is prepared in `deploy/install-cbot.sh`, with optional next
step `deploy/publish-cbot.sh` for DNS-checked Nginx/Certbot publication. It uses
Coin's local authenticated read-only feed, separate CBot wallet/token/user and
ports 8503/8766. Eleven bot tests plus three dashboard fixture scenarios pass;
installer rehearsal passed without service changes. CBot was subsequently
deployed at `/opt/cbot/releases/20261106T191021-33085`, recorded a simulated SOL
buy, passed HTTPS health checks, and was visually confirmed by the user.
PBot dual sandbox deployment at `/opt/pbot/releases/20261106T185718-32563`
was confirmed with two fresh prediction feeds and separate $1,000 virtual wallets.
No live orders.

Betting Lab is separately hosted at OpenAI Sites/Cloudflare Workers, original
URL `https://shane-betting-lab.oaken-sage-8204.chatgpt.site`. Its bets.shaneathon.com
custom domain initially had routing/TLS delays, then the user confirmed it
working. The requested compact suggestion-reasons accordion must be edited in
the original Betting Lab chat; this repository does not contain that app's code.

Current task is the protected apex portal, prepared in `portal/`. Root DNS
currently has four Squarespace A addresses (198.49.23.145, 198.49.23.144,
198.185.159.144, 198.185.159.145). Replace only apex A records with the droplet
165.22.162.116; preserve all subdomain/email records. No apex host exists in
the droplet's Nginx sites-enabled output. `portal/install.py` prompts privately
for credentials and checks 401/200 behavior after HTTPS activation. Deployment
is not yet confirmed. After portal completion, expand data collection last.

Later confirmed: portal HTTPS was issued and a local unauthenticated check
returned 401; the user successfully logged in and said it worked great. Keep
its server-side auth and private password files unchanged. The initial post-
reload certificate check had a transient hostname mismatch; do not rerun the
non-idempotent installer over the now-working portal.

Current request: extensive strategy research for Polymarket crypto predictions
and Coinbase spot entries/exits, then paper testing across all supported markets.
Research package is in `research/strategy/` (15 retrieved SDK/engineering
sources, source hashes, 15 versioned candidates, explicit evidence limits and
cost calculators). Full exchange docs/academic sites were inaccessible; do not
claim those original papers or current fee tiers were verified.

Prepared, not yet confirmed deployed: `deploy/expand-pbot-markets.sh --apply`
preserves Champion/B BTC control wallets and adds 10 independent market-local
research wallets using the generic research model. Fresh crypto streams may
enter; missing metals remain paused. ALL use explicitly hypothetical 50c
reference/costs; executable quote mapping/fills are still unfinished.
`deploy/install-market-capture.sh --apply` adds a resource-capped, public-only
Coinbase raw WebSocket recorder with compressed segments and lifecycle/gap
logs. No trading keys. Its actual public channel availability must be checked
on the droplet. Raw capture is not a validated tradable book. Existing CBot
already paper-trades all four spot products. No real trading is authorized.

Subsequent droplet output confirmed the all-market update at
`/opt/pbot/releases/20261106T214907-36567`: eight crypto streams MONITORING,
gold/silver PAUSED_NO_FRESH_PREDICTION, original control ledgers preserved.
The raw recorder was installed, received trades, then disconnected. Isolated
public probes confirmed heartbeats and market_trades work; level2 immediately
closed with code 1006, cause unknown. Recorder defaults have been changed to
the two working channels; `deploy/update-market-capture.sh --apply` is prepared
for a recorder-only update, not yet confirmed deployed. Existing REST book
collection remains; full streamed Level-2 and tradable-book validation remain
unfinished. Do not describe current raw capture as a validated book.

Later recorder-only update was confirmed deployed at
`/opt/coinbase-recorder/releases/20261106T215517-37030`: CAPTURING_RAW, 91 trade
messages, 10 heartbeats, no reconnects in that session, Level-2 excluded.
User enabled DigitalOcean daily backups; screenshot confirms enabled, window
08:00–12:00 UTC (02:00–06:00 Central on this date), first completion not yet
verified. Do not claim a completed provider backup from an enabled schedule.

Current task: consistent app/database backups and health checks, prepared in
`operations/` and `deploy/install-maintenance.sh`. Seven tests and installer
rehearsal pass. Not yet confirmed deployed. Hourly private SQLite snapshots
with integrity checks and bounded retention; daily GET-only Supabase public
data exports; health checks every five minutes and protected /health.html.
No application services are stopped/restarted. No credential values in
archives/logs. External push notifications and full disaster restore tests
are not configured. Managed backups supplement these local snapshots.

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
