# CBot — Coinbase crypto paper trading

Target hostname: **cbot.shaneathon.com**. This assumes the same `.com` domain as
btc.shaneathon.com and pbot.shaneathon.com. CBot is a separate spot-trading bot,
not a Coinbase version of Polymarket's expiring UP/DOWN contracts.

Initial products: BTC-USD, ETH-USD, XRP-USD and SOL-USD. This is a configurable
starting scope in code, not every Coinbase-listed crypto. There is no leverage,
short selling, staking, withdrawal or real-order path.

## First development release

- Public Coinbase Advanced product metadata, one-minute candles and top-of-book
  data, with no account or trading key. Routes/types checked against the official
  coinbase-advanced-py **1.8.4** wheel; live responses remain unverified here.
- Strict product/base/quote/spot-status checks, completed contiguous candles,
  finite OHLCV, source-timestamp freshness and exact-product order books. One
  product outage is visible without blocking other products' data collection.
- Independent persistent USD paper wallet, spot holdings, trade history, stored
  one-minute candles and book observations. It never uses Polymarket targets,
  payouts, probability estimates, ledger balances or model scores.
- Experimental EMA9/21 + three-minute momentum strategy: BUY rising aligned
  momentum; SELL owned holdings on falling aligned momentum or modeled stop-loss
  /take-profit thresholds. No short entries or retrospective best-price fills.
- Buys at ask plus modeled slippage, sells at bid minus modeled slippage, and
  percentage fees on both sides. Sizing respects cash, product increments/minima,
  available top-level size, cost/exposure and reserved worst-case loss budgets.
- Duplicate-candle prevention, restart persistence, post-exit cooldown, UTC daily
  risk budget, realized/cost-basis drawdown and an entry kill file. Modeled exits
  remain possible during a kill switch but require fresh valid data and depth.
- Separate dashboard, price charts, portfolio, decision state, risk and live
  readiness. Separate CBot token, port and service templates. Read-only status
  transport/ledger-validation utilities are shared code, not shared accounts.
- Explicit venue checks prevent a CBot UI from treating a PBot response as its
  account. Foreign/config-incompatible ledger files are rejected before schema
  writes. Status endpoints have no order/mutation routes.

## Limits and paper assumptions

The example starts at $1,000 virtual cash and $50 maximum position cost. Fees
(0.6% each side), slippage (0.05%), 2% modeled stop, 4% modeled profit target,
spread/risk limits and cooldown are **research examples**, not the user's actual
Coinbase fee tier, an optimized strategy or evidence of profitability.

Poll interval is 60 seconds. Stops/take profits are modeled decisions after a
poll, not resting exchange orders or guaranteed levels. Missing/stale/corrupt
feeds or inadequate exit depth can prevent a modeled exit. The engine uses
realized/cost-basis risk accounting rather than real-time bid-marked drawdown.
Fills do not model queue priority, market impact or real partial executions.

No empirical historical-performance gate or automatic optimization has been
implemented for this prototype. Evaluation against collected Coinbase data and
prospective paper results is required before any strategy claim. Paper success
never enables live orders. Live submission always raises LiveTradingDisabled.
The payload helper is not a production live broker.

## Local development

From the existing repository checkout (no extra worktree needed):

```bash
python3 -m unittest discover -s coinbase_bot/tests -v
# Install coinbase_bot/requirements.txt for the separate UI:
python3 coinbase_bot/smoke_ui.py
streamlit run coinbase_bot/app.py
```

CBot starts in SETUP with no fabricated balances or trades. To run the PAPER
engine after public data access is validated:

```bash
python3 -m coinbase_bot.runner --ledger /path/cbot-paper.sqlite \
  --config coinbase_bot/paper.example.json --kill-file /path/STOP --loop
```

The runner's optional `--snapshots` JSON path is for reviewed offline fixtures,
not a substitute for live feed verification. Configuration is frozen per ledger;
intentional new experiments use separate ledger files.

## Hosting and connection requirements

`deploy/install-cbot.sh --prepare` rehearses the isolated installer and checks.
`--apply` creates only CBot's user, units and persistent paper wallet. It tests
the existing Coin tracker first, then configures a private copy of its read-only
API token for the engine; no exchange trading keys are used. Engine/API/UI have
separate environment files so the public dashboard receives no Coin feed token.
The runner uses `--tracker-url http://127.0.0.1:8767/status`, avoiding duplicate
Coinbase requests. Existing collectors, Coin and PBot are not reconfigured.

The paper wallet starts with $1,000, up to $50 per position and the stricter
remaining exposure/loss budgets. Example costs are 0.6% fee and 0.05% slippage
per side, not a verified user fee tier. Simulated stop/take-profit/trend exits
are checked about once per minute using fresh sampled books; they do not
guarantee execution prices or model intraminute paths. Data outages fail closed
for fills. Decisions/skips are retained in `decision_journal` for later review.
Strategy profitability has not been established; real submission stays disabled.

After adding the cbot A record, `deploy/publish-cbot.sh` checks that DNS points
exclusively at the current droplet, checks CBot health, creates only its new
Nginx host, validates before graceful reload, and uses existing Certbot account
configuration for HTTPS. It refuses existing host files rather than replacing
them. If DNS has not propagated, services remain installed and publication
can be retried separately. Existing btc/coin/pbot hosts are untouched.

Prepared templates in deploy/ use /opt/cbot, a dedicated cbot identity and
/var/lib/cbot. PBot uses /opt/pbot and /var/lib/pbot with separate credentials.
CBot API/dashboard ports are 8766/8503; PBot uses 8765/8502. Deployment must copy
the repository modules used by both apps' read-only transport helpers, not only
one app.py file. No service was created or started here.

Privately generate an independent CBOT_READ_TOKEN and configure CBOT_STATUS_URL.
No Coinbase trading credentials are needed for public paper-data collection.
The API binds loopback. Its dashboard may share a host or use an explicitly
configured authenticated HTTPS status service. The public app does not receive
Coinbase signing keys. A separate Nginx hostname template is provided; real DNS
and TLS require the actual hosting account/endpoint and remain unconfigured.

The environment currently denies public api.coinbase.com requests. That hostname
was added to the saved environment draft, but a draft save does not apply or
publish the network policy. Coinbase source validation can instead happen from
the authorized droplet when connecting later; no firewall bypass is attempted.

## Future live broker

Order-payload preparation follows the official SDK's client_order_id/product_id/
side/order_configuration format. Real submission is unavailable. A later release
needs explicit authorization, account/region/product permissions, actual fees,
precisions, balances, signed authentication, durable intent/order/fill recovery,
unknown-result handling, partial fills/cancellations and real live risk controls.
Do not insert private keys into app configuration or Git to enable this prototype.

## Validation

Nine Coinbase tests pass: product/candle/book checks, independent feed failure,
spot buy/sell costs, restart idempotence, kill/stale/depth checks, risk/increments,
foreign-wallet rejection and disabled live submission. Three Streamlit fixture
cases pass: setup, connected synthetic portfolio/charts and outage. These are
synthetic functionality tests, not actual Coinbase trades or strategy results.

## Resume

> Continue PBot and CBot from bot/pbot-cbot-terminals. Use pbot.shaneathon.com for
> Polymarket and cbot.shaneathon.com for Coinbase. Keep both paper-only, preserve
> BTCandThings and existing collectors, and connect data and hosting safely.
