# BTCandThings, PBot, CBot and Coinbase tracker handoff

Repository: Shaneathon/BTCandThings. Current preparation branch:
`tracker/coinbase-research`.

## Latest user runtime evidence and prepared cache fix

Observed migration completed successfully around 2026-11-07 01:32 UTC, user
visually confirmed both dashboards. CBot release /opt/cbot/releases/20261107T013213-44072.
User later reported SOL5m observed paper partially-filled remainder-cancelled
order settled loss1.00 + fee.06 = net loss1.06, wallet998.94, no open position.

User requested verification after seeing historical PBot skip events. Read-only
`trading_bot.verify_runtime` added and run by user. Returned excerpt confirms:
CBot status age1.8s, four FILLED orders, no overdue proposals, accounting exactly
reconciles: cash900.0192095358722 + open99.3259410950354 =1000-0.6548493690924.
LiveFalse, all listed original collectors and bot services active. User pasted
only tail of PBot report; cannot certify all its wallet accounting from that tail.

Important public book evidence: exact BTC15m contract response has 50 bid and47
ask levels, OPEN, CF-Cache-Status HIT, Cache-Control public,max-age=30, Age16.
Thus strict five-second freshness rejection is appropriate. Request no-cache
headers alone did not prevent cached responses. Old skip table records distinct
first observations, not present health/retry counts. Paired-control check can
log missing signal before entry window, so don't infer a broken bot from it.

Prepared but not yet user-applied: `deploy/fix-pbot-book-cache.sh --apply`.
It first sends ONE public cache-keyed query probe via verify_runtime --cache-probe;
requires exact-contract valid book, current window and fresh Date/Age <=5s before
any service modification. Respects known bot request cooldown/spacing; if skipped
or invalid exits with services untouched. If successful prepares immutable PBot
source release reusing installed venv through a symlink, tests it, changes only
PBot unit paths and restarts engine/status/UI. Same ledger/config and limits;
no wallet reset or financial rule changes. Falls back to prior units on startup
failure. Coinbase/collectors/ops health unit unaffected. Existing freshness
checks remain strict for every request, even after probe success.

New helper `trading_bot.book_request.request` adds an opaque UUID query key and
standard no-cache headers. This ordinary HTTP cache-key technique is conditional
on the actual provider accepting it; never claim guaranteed bypass from code
alone. Root development environment cannot reach gateway; user-run probe proves
response behavior. If unsupported/ignored and stale, stop and investigate another
provider-supported fresh transport; do not loosen quote ages or allow stale fills.

## Prepared observed-price migration — NOT YET deployed

User explicitly expanded realism work to BOTH Polymarket and Coinbase. Future
$5–10 real-money experiment discussed only conditionally; real submission is
still disabled and not authorized by this migration.

`deploy/activate-observed-paper.sh --apply` is the prepared ONE-block deployment
for both bots. First creates/tests fresh immutable releases, preserves all old
histories/configuration/tokens, verifies startup/live-disabled mode, then updates
health markers to new ledgers. It refuses existing observed ledgers and unsettled
old PBot positions; do not retry by deleting either. New ledgers:
`/var/lib/pbot/observed-v1.sqlite`, `/var/lib/cbot/observed-v1.sqlite`.
Old Coinbase virtual open positions remain archived, not transferred. Each new
wallet starts independently at $1,000; PBot has 12 comparison/research wallets,
CBot one shared spot wallet across four products. No collectors restart.

PBot source `trading_bot/observed_paper.py`: persistent reservations/proposals,
post-delay books, IOC partial/unfilled outcomes, official settlement once,
per-market complete-history P/L, original Champion/B fresh paired-control gate.
Provider adapter `provider.py` uses typed current terms + explicit Up-if>=
description + Yes LONG/No SHORT identifiers + resolved-cohort corroboration
(>=3 distinct, both UP and DOWN, no conflicts). Complementary SHORT model is
explicit. REST Date/Age/request latency used for snapshot freshness;
transaction timestamp can be old on unchanged book. New pause file STOP-OBSERVED.
Old STOP-SANDBOX stays present. Quote archive budget 1GiB plus 4GiB free floor.

Fee basis was clarified by subsequent user-relayed support: published taker .06,
quadratic c*q*p*(1-p), HALF_EVEN per execution. Use .06 as explicit published-
schedule paper basis; retain observed API .095 and fee sensitivity per position.
No maker rebates credited. API override applicability still unconfirmed, not
silently treated as resolved. One simulated execution per price level means
real fill partition rounding may differ.

CBot `coinbase_bot/observed.py`: same existing signal/risk strategy, durable
frozen Coinbase limit_limit_fok instructions, >=2s delay/later sampled book,
45s expiry, best-level 25% participation, FOK unfilled at limit/size failure,
separate new ledger. 0.6% fee per side is STILL explicitly estimated, not an
actual account fee tier. Old 5bps parameter is limit allowance, not an invented
fill-price markup. Runner polls local Coin feed every5s, handles outage without
fabricating fills; no extra Coinbase requests. Both shared order-instruction
helpers exist but actual live submission still raises disabled errors.

Full release rules and limits: research/execution/OBSERVED_PAPER_V1.md. Previous
pending notes below are historical; code is now prepared beyond their state.
User confirmed old P/L dashboard migration at /opt/pbot/releases/20261107T010608-43106:
ChampionBTC15m124.64, Challenger134.52, all old fixed-price open exposure0.
Do not report these as live-equivalent profit or import them into new results.

## Pending paper-execution realism migration — November 7, 2026

User explicitly requests paper results based on actual market prices, with the
same decisions/order instructions as a future live bot. NO REAL TRADING.
Previous fixed-50c profits (user reported +$124) are not attainable-profit proof.

Prepared, tested but NOT YET run on the droplet:
`deploy/prepare-pbot-realism.sh --apply`. It pauses new artificial entries with
STOP-SANDBOX, preserves all existing histories and ongoing settlements, then
runs a public read-only exact-contract `/book` and metadata audit. No service
restart, collector change or new realistic execution engine is implied.
Private results: `/var/lib/pbot-execution-audit/latest.json` and per-stream raw
metadata/book JSON. User should return the printed report. The environment
cannot access DigitalOcean directly or the gateway under its network policy.

Next: review mapping, quantity units, book freshness, fee formula/ticks/minimums
using actual evidence, then build/validate the shared proposal and simulated
execution adapter and publish a NEW forward ledger. Do not re-enable 50c entries
or present the diagnostic as the finished replacement. Full requirements:
`research/execution/REALISTIC_PAPER_PLAN.md`. CBot is unchanged and retains its
sampled real quote/assumed-cost limitations.

### Audit received; accounting and execution primitives prepared

User returned AUDIT_COMPLETE. Observed XRP5m exact contract LONG book has real
prices/quantities; metadata has Yes/long=true and No/long=false, feeCoefficient
0.095, tick0.01, minimum quantity0.01. Transaction timestamp was ~29s old despite
fresh REST reception. Do not equate last book mutation time with REST freshness
without checking snapshot/cache semantics. These fields do not yet prove fee
formula or directional mapping. No new execution bot has been activated.

Prepared next deployment `deploy/update-pbot-market-report.sh --apply` updates
only PBot code/units, requires STOP-SANDBOX already present, preserves that pause
and all ledgers. It displays complete-history P/L by wallet and market, including
zero-entry streams, separate gross/assumed fees/net and open cost. Historical
fixed-price labels remain prominent. Collectors/CBot unchanged. Not yet run by
user at time of commit.

`trading_bot/execution_model.py` now contains a common immutable order spec and
an offline depth simulator (post-delay books, limit/size/TIF, FOK rejection or
IOC partial fill, max25% participation). Tested offline only. It is NOT a
persistent runner or an active trading adapter. Only a synthetic reviewed-flat-
fee rule exists for tests; do not use .095 as that parameter. Production fee
formula, semantic mapping, short conversion, persistent reservation/idempotence,
book acquisition and realistic-ledger/UI integration remain to finish.

## Current confirmed status — November 6, 2026

This section supersedes historical preparation notes below. Last server evidence:
2026-11-07 00:33:28 UTC (November 6, 6:33 PM Central). Do not infer current runtime health
forever from this timestamp; recheck before deploying or reporting live status.

- btc.shaneathon.com, coin.shaneathon.com, pbot.shaneathon.com and
  cbot.shaneathon.com have HTTPS and user visual confirmation.
- bets.shaneathon.com works; it is hosted separately on OpenAI Sites/Cloudflare,
  with code accessible from its original ChatGPT app conversation, not this repo.
- shaneathon.com portal works with server-side password protection. Username
  is Shaneathon; password is private and never belongs in chat/Git. Portal
  protection does not restrict direct access to individual dashboards.
- All 15 monitored services, including the metals sampler, were active in the latest health output. Original
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
  set successfully backed up and integrity-checked **19 databases**, including
  the metals cache, at 2026-11-07 00:33:28 UTC. The pinned-snapshot fix resolved
  the earlier Coinbase copy timeout; latest backup and health states are OK. Hourly SQLite snapshots, daily
  Supabase public-data exports and five-minute health timers are enabled.
- First cloud export subsequently completed successfully at 23:48:07 UTC:
  402 btc_markets rows, 24,226 btc_predictions rows and 5,205 Challenger rows.
  Its earlier pending-export warning should clear at the next health run.
  These are private local exports of cloud rows, not a full Supabase schema/PITR backup.
- Root disk had 40.12 GiB free and memory 933 MiB available in that output.
- Private health report: https://shaneathon.com/health.html. Alerts are local
  journal/report only; no email/SMS/webhook notifications are configured.
- **Real trading is disabled and not authorized.** User authorizes autonomous
  versioned paper experiments, but a self-optimizing promotion controller has
  not been implemented. Keep baselines frozen and never rewrite results.

Next check: first completed DigitalOcean backup. Local database snapshots and
first cloud-data export are confirmed successful.
Remaining development: verified Polymarket mapping/quote-realistic fills, metals
feeds, validated Level-2/replay, autonomous experiment review/promotion, optional
external notifications, full restore rehearsal. Betting Lab accordion change
must be confirmed in its original app conversation. Keep manual steps minimal.

Metals follow-up: user supplied live contract descriptions confirming Chainlink
XAU/USD-Streams-ForexPrice (2 decimals) and XAG/USD-Streams-ForexPrice (3 decimals).
User's two unauthenticated Gold-API checks returned USD/XAU 4072.100098 and
USD/XAG 52.070999 with fresh source timestamps near 23:54 UTC November 6.
Prepared in `metal_proxy/` and `deploy/install-metals-proxy.sh`, not deployed yet:
a private sampled spot-quote cache/API, 50-contiguous-minute warm-up, no fake
backfill/volume, strict source timestamp handling, explicit proxy provenance.
Official targets/settlements remain Chainlink. Installer updates only the
multiasset research reader plus maintenance code; Champion/Challenger, Coin
and paper engines keep running. Separately hosted tracker wiring still needs
verification; do not claim website charts were deployed by this script.

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


## Latest maintenance/metals follow-up

Metals sampler installation was confirmed, with both sources receiving fresh
quotes and warming up at 2026-11-07 00:20 UTC. Research release:
`/opt/btcandthings-research/releases/20261107T001947-40910`; maintenance release
then `/opt/shaneathon-ops/releases/20261107T002021-41210`. Hosted tracker data
wiring is not confirmed by this backend installation. Paper slots require
50 valid contiguous minute bars plus a current verified market.

Health at 00:20:23 UTC flagged Coinbase status stale and the most recent local
backup failed. Subsequent Coinbase logs at 00:22:36 and 00:22:55 show all four
products healthy again; do not restart it merely because of the older report.
Backup log: 00:00 run timed out after 120 seconds copying the actively written
Coin database. Prior 18-database backup and cloud export remain intact.
A pinned read-transaction backup fix with a five-minute deadline is prepared;
eight maintenance tests pass, including concurrent writer commit/snapshot
consistency. It is not yet confirmed deployed. Next action: update maintenance,
retry only the backup job, then refresh health. No bots/collectors restart.


Confirmed follow-up: pinned-snapshot maintenance update deployed at
`/opt/shaneathon-ops/releases/20261107T003139-41781`. Eight server tests passed.
Backup retry completed 19 databases at 00:33:28 UTC; health state OK, all 15
services active, fresh status ages (research 68.3s, Coin 9.5s, PBot 1.0s,
CBot 53.7s). Only GOLD_15m/SILVER_15m paused notices remain. Sampler started
near 00:20 UTC, so warm-up had not completed; actual candle counts/readiness
and valid current contracts still need checking after sufficient history.

## Fee clarification from user-supplied Polly support messages

Polly reports published US taker coefficient .06, maker rebate .0125, formula
coefficient * contracts * price * (1-price), price .01..99, fees per execution,
nearest-cent HALF_EVEN (banker's rounding). Polly did NOT confirm whether
market API feeCoefficient .095 overrides .06. Exact evidence user supplied:
GET https://gateway.polymarket.us/v1/market/slug/cpcxrp-xrp-updown-5m-2026-11-07-0055z
response market.feeCoefficient=0.095 (audit extracts fee_coefficient). Need
provider answer; no account credentials needed. Formula implemented/tested in
execution_model.taker_fee; no production coefficient selection or activation.
Simulated level fills disclose ONE_SIMULATED_EXECUTION_PER_CONSUMED_PRICE_LEVEL:
aggregate books cannot reveal actual execution partitions, hence rounding can
differ from real exchange fees. Maker rebates not assumed for taker fills.

### Cache probe succeeded; first update stopped safely at test packaging

User ran fix-pbot-book-cache.sh. Fresh query for BTC15m0200z returned
CF MISS, Age absent, Date/transaction current at 2026-11-07T02:07:04Z,
58 bids/41 offers, fresh_response_verified true. Provider accepts this query.
Then isolated release cache-20261107T020704-45982 failed test import because
verify_runtime tests import coinbase_bot.observed but bundle copied only
trading_bot. Failure occurred before unit edits/restarts, so old running bots,
ledgers and balances were unchanged. No need to delete failed release or ledger.

Fixed BOTH fix-pbot-book-cache.sh and start-pbot-sandbox.sh preparation copies
to include coinbase_bot Python package required by diagnostic tests. Verified
using the actual embedded copy code into an isolated temporary release (not
checkout imports): all46 PBot tests plus UI smoke checks pass. User should fetch
and rerun the same cache-fix command; fresh probe still gates any service change.
