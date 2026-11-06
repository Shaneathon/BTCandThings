# BTCandThings, PBot, CBot and Coinbase tracker handoff

Repository: Shaneathon/BTCandThings. Current preparation branch:
`tracker/coinbase-research`.

## November 6 session priorities and authorization

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
