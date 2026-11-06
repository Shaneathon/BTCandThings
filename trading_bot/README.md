# PBot — independent ten-market paper terminal

Target: **pbot.shaneathon.com**, separate from btc.shaneathon.com. This is the
first bot-development release, on branch `bot/pbot-cbot-terminals`. It has not
been deployed or connected to any live account. No existing tracker, production
service or database is changed by this increment.

## What is implemented

- Persistent paper wallet, positions and decision journal in a dedicated SQLite
  ledger, separate from collector databases. Transactions serialize entries and
  settlement; a market may be traded only once per ledger, even after restart.
- All ten streams: BTC/ETH/XRP/SOL × 5m/15m and GOLD/SILVER × 15m.
- Per-model, per-asset, per-duration and per-elapsed-stage historical gates. Each
  historical market contributes only its first valid prediction in that stage.
  Only results already officially settled at decision time qualify. No future
  source observations, current-market result, foreign-asset statistics or
  hindsight-selected winning predictions enter that gate.
- Entries require fresh model predictions, matching lean, finite probability,
  verified target, a fresh exact-contract mapped quote, acceptable spread and
  modeled edge after fee/slippage assumptions. Size is limited by quoted ask
  depth, available cash, per-trade cost, aggregate exposure, open-position count,
  and remaining daily/drawdown worst-case-loss budgets. Fill is all-or-none in
  paper at ask plus slippage; this is not an exchange queue/latency simulator.
- Positions are held to official settlement; early exits and stop-loss orders
  are not implemented. Verified matching official outcomes close paper positions and pay at most
  once. Unknown, premature, foreign-contract or changed-target results cannot
  pay. The kill file stops new entries but allows settlement to continue.
- Realized-loss/cost-basis drawdown accounting, not bid-marked equity or trailing
  stops. A drawdown halt persists. Daily risk uses UTC dates and reserves the
  worst-case cost of open positions. No automatic policy reset is provided.
- Independent Streamlit dashboard: ten-market board, paper wallet/portfolio,
  decision journal, risk configuration and live readiness. Setup and data outages
  are explicit; missing account data is not presented as real performance.
- Bearer-authenticated read-only status API on loopback. No trade/mutation routes,
  no credential logging, no browser-side account credentials.

## Strategy defaults are paper assumptions

`paper.example.json` starts with $1,000 virtual cash, $10 maximum cost per trade,
$100 aggregate exposure, at most ten open positions, $100 daily risk and 10%
maximum realized drawdown. Minimum history is 30 independently settled markets
**per stream/model/stage**, baseline Brier <=0.25 and net modeled edge >=0.05.
Fees and slippage are illustrative $0.01/share each, not verified exchange fees.
These parameters are neither optimized nor evidence of profitability.

The current default model is the collected `Multi-asset spot baseline research
V1`, not a validated strategy and not the production BTC Champion. Existing
Champion/Challenger collectors stay unchanged. No extra Challenger models are
needed. Paper statistics do not automatically authorize live trading.

Configuration is frozen with each ledger. Changing it requires an intentional
new experiment/ledger; open positions and historical balances are never silently
reinterpreted under new parameters. A drawdown halt requires explicit review,
not deleting ledger rows or automatic restarting to reset risk.

## Local development

From the repository root, with the existing website dependencies or the separate
`trading_bot/requirements.txt` installed:

```bash
python3 -m unittest discover -s trading_bot/tests -v
python3 trading_bot/smoke_ui.py
streamlit run trading_bot/app.py
```

The app initially shows SETUP; it does not create fake trades or start an engine.
Fixture tests use explicit synthetic records and reduced minimum-history values;
they do not constitute historical results or proof of an edge.

Paper engine, once real collector data and mapped quotes are available:

```bash
python3 -m trading_bot.runner \
  --collector-db /path/to/research.sqlite --ledger /path/to/pbot-paper.sqlite \
  --quotes /path/to/reviewed-quotes.json --config trading_bot/paper.example.json \
  --kill-file /path/to/STOP --loop
```

The collector DB is read-only and cannot also be the ledger path. A normalized
quote must contain market_slug, contract_slug, captured_at, source_name=
Polymarket US, side_mapping_verified=true, documented side_mapping_evidence,
up/down bid/ask and up/down ask_size. Raw BBO records with an unverified mapping
cannot fill. The quote producer is not connected yet. Input errors stop that
cycle rather than invent data; a managed runner can retry after recovery.

## Live trading: preparation, not capability yet

`live.py` builds reviewed-contract-mapped SDK 2.4.1 limit-order payloads and has
an injected authenticated SDK preview interface. `submit()` always raises
LiveTradingDisabled. The paper engine never imports or calls the live gateway.
There is no LIVE switch, exchange secret, trade button or real-order CLI.

Actual live execution still needs a separately reviewed release: explicit user
activation, authenticated account/eligibility checks, funded balance checks,
per-contract/tick/quantity rules, fees, persistent order IDs, crash-safe intent
journaling, submitted-order reconciliation, partial fills, cancellations,
unknown-result recovery, exchange rate limits and live risk controls. Paper
fills must never be represented as confirmed live fills. No exchange account
was contacted during this development.

## Deployment preparation

### Additional all-market directional experiments

After the dual sandbox is installed, `deploy/expand-pbot-markets.sh --plan`
rehearses a release and `--apply` updates only PBot units. It preserves both
original Bitcoin control configurations and ledger history, and adds separate
market-local research wallets for all ten listed
streams. They use `Multi-asset spot baseline research V1`, not fabricated
Champion/Challenger outputs for other assets. Gold/silver slots remain paused
when metadata or fresh forecasts are missing. No unsupported metals 5m slots
are created. A shared STOP-SANDBOX file pauses entries in all experiments.

The exporter reads recent local research snapshots read-only. A legacy BTC
prediction endpoint outage no longer blocks independent local research feeds
in all-market mode. Each new wallet is independently versioned and uses the
same explicitly hypothetical 50c/cost model as described below. This does not
finish quote mapping, make liquidity real, or turn twelve experiment wallets
into one combined funded portfolio. Live and executable-quote fills stay off.

### Forward Champion versus Challenger B directional sandbox

`deploy/start-pbot-sandbox.sh --prepare` rehearses an isolated release;
`--apply` updates only an existing observation-mode PBot. It backs up the
three PBot units, starts a separate root data-export timer, and restarts the
PBot engine/API/dashboard. It never restarts the collectors or Coinbase stack.
Immediate PBot startup failures restore the prior observation units.

This experiment uses separate `champion-directional-v1.sqlite` and
`challenger-b-directional-v1.sqlite` virtual wallets under `/var/lib/pbot`,
with $1,000 each, $10 maximum entry cost and one open BTC 15m position each.
The entry window is 90–30 seconds before expiry. Both model signals must be
present, nonfuture and at most 90 seconds old, and the export no older than
45 seconds. The entry is recorded at actual observation time; closed markets
are never retrospectively entered. An entry needs at least 55% model confidence.
Official verified settlements, including contract, target and window checks,
close positions exactly once. A $100 daily loss budget and 10% drawdown halt
remain active; `/var/lib/pbot/STOP-SANDBOX` pauses entries, not settlements.

**Prices are hypothetical:** 50c reference, plus 1c slippage and 1c fee per
share. There is no assertion of real order-book liquidity, UP/Yes mapping,
executable fills or realistic profitability. These assumptions are prominently
shown on the dashboard. Actual-quote fills and live orders remain disabled.
This lets the user compare forward directions while quote integration remains
unfinished. It must not be presented as a realistic trade simulation.

The root exporter reads public prediction records via GET using the existing
private collector environment and reads the research DB read-only. It exports
only public BTC metadata/predictions to a separate atomic root-owned 0640 file
readable by pbot. The engine/API/dashboard receive no Supabase credentials.
Signal observations are archived for later entry-timing analysis. Settled
losses receive automated descriptive classifications; normal losses are not
automatically treated as strategy mistakes. This version does not optimize
rules or self-modify. New changes must preserve a frozen baseline and use a
separately versioned experiment/ledger. The user has authorized autonomous
paper-only experimentation; real-money activation is not authorized.

`deploy/install-pbot.sh --prepare` rehearses an independent installation.
`--apply` installs **observation mode only**: a separate virtual ledger,
authenticated loopback status API on 8765, and dashboard on 8502. Paper entries
are hard-disabled in `trading_bot.monitor`, regardless of files or configuration.
The normal paper runner is not started. Quotes are not assumed to be mapped.

A dedicated root oneshot/timer reads only public research records from the
collector SQLite database and atomically exports a snapshot every 60 seconds.
The pbot user can read that separate root-owned snapshot, but receives no
collector credentials, database permissions or write access. Stale snapshots
are explicitly marked and excluded after 180 seconds. Existing collectors
are neither restarted nor reconfigured. Enabling paper fills will require a
separate implementation/update after quote mapping and execution checks pass.
DNS, Nginx and HTTPS are configured separately after service health checks.

The three service templates in deploy/ run a distinct paper engine, status API
and dashboard as a dedicated pbot user, using /opt/pbot and /var/lib/pbot. They
are templates only; no user or systemd unit was created or started here.
The Nginx template adds a separate hostname and never replaces the BTC host.

Before activation, validate server capacity, configure the new user/venv/state
and private token, and arrange narrowly scoped READ access to the new collector
DB (or a reviewed read-only snapshot). The collector currently uses a separate
protected service identity; do not chmod credentials/databases world-readable,
run the bot as root, or change existing Champion/Challenger permissions to make
access work. The prepared quote adapter still needs verified mappings/depth.

DNS and TLS for pbot.shaneathon.com require the actual hosting endpoint and
account access. No DNS record, certificate, host route or deployment has been
created. The dashboard can alternatively be hosted as a separate Streamlit app,
with a privately configured HTTPS status endpoint; it must not assume that
Streamlit's ephemeral filesystem shares the droplet's persistent ledger.

## Checks completed

16 bot tests pass: all-ten entries, wallet/exposure, repeated-cycle and restart
idempotence, official-only payout, incorrect/future settlement rejection, stale
and unmapped quotes, independent history/Brier gates, worst-case daily budget,
kill switch, persistent drawdown halt, clock rollback, live submission denial,
real temporary-loopback API authentication/read-only behavior, and the actual
collector-format runner producing a separate ledger without changing source bytes.
Three Streamlit fixture checks pass: unconnected setup, connected synthetic
portfolio, and status outage. Existing tracker and collection tests remain
separate. This does not establish live API compatibility, fee correctness,
liquidity execution or production readiness.

## Resume phrase

> Continue PBot from bot/pbot-cbot-terminals for pbot.shaneathon.com. Connect
> the ten-market paper engine to the prepared collector and verified quotes,
> preserve the existing BTC tracker and collectors, and keep real orders disabled.
