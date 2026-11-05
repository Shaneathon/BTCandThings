# TBot — independent ten-market paper terminal

Target: **tbot.shaneathon.com**, separate from btc.shaneathon.com. This is the
first bot-development release, on branch `bot/paper-trading-terminal`. It has not
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
  --collector-db /path/to/research.sqlite --ledger /path/to/tbot-paper.sqlite \
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

The three service templates in deploy/ run a distinct paper engine, status API
and dashboard as a dedicated tbot user, using /opt/tbot and /var/lib/tbot. They
are templates only; no user or systemd unit was created or started here.
The Nginx template adds a separate hostname and never replaces the BTC host.

Before activation, validate server capacity, configure the new user/venv/state
and private token, and arrange narrowly scoped READ access to the new collector
DB (or a reviewed read-only snapshot). The collector currently uses a separate
protected service identity; do not chmod credentials/databases world-readable,
run the bot as root, or change existing Champion/Challenger permissions to make
access work. The prepared quote adapter still needs verified mappings/depth.

DNS and TLS for tbot.shaneathon.com require the actual hosting endpoint and
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

> Continue TBot from bot/paper-trading-terminal for tbot.shaneathon.com. Connect
> the ten-market paper engine to the prepared collector and verified quotes,
> preserve the existing BTC tracker and collectors, and keep real orders disabled.
