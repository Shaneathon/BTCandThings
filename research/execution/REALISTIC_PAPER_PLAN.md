# Execution realism migration

Authorized: paper-only changes. Real submission remains unavailable in
`trading_bot.live.LiveGateway.submit`. No exchange trading keys are required.

The previous fixed-50-cent PBot is a directional prediction experiment. Its
profits are not evidence of attainable live profits. Preserve its ledgers and
stop new artificial-price entries with `/var/lib/pbot/STOP-SANDBOX`; its running
service continues official settlement accounting. Do not delete that file while
migrating, and do not mix those results into the new execution ledger.

## Prepared first deployment step

`deploy/prepare-pbot-realism.sh --apply` pauses new fixed-price entries and runs
`trading_bot.execution_audit`. It does not install a replacement engine yet.
This is necessary because the running host can reach the public market gateway;
the development environment does not have that host allowed or DO credentials.

The audit reads the research database with SQLite read-only mode and requests
current exact-contract public metadata and `/book`, at most ten streams, with
no authentication and no order endpoints. It validates asset/window/target,
open book state, USD prices and positive finite quantities, checks timestamps,
and records small top-of-book samples plus private raw responses. HTTP 429
stops the probe and persists Retry-After (at least sixty seconds). Neither BBO
depth counts nor a missing book are substituted for executable quantities.

Private evidence is in `/var/lib/pbot-execution-audit/`. `latest.json` reports
remaining blockers. Yes/No labels do not silently become verified UP/DOWN
mapping. `feeCoefficient` is recorded, not interpreted as a verified fee formula.
An old exchange transaction timestamp can mean an unchanged quiet book rather
than a broken feed; distinguish verified current snapshots from stale cached
responses before choosing the production freshness rule.

## Replacement execution requirements

1. Resolve direction mapping from official contract semantics and corroborating
   settlement evidence. Verify LONG/SHORT complement-price conventions and
   quantity units using official provider definitions and actual response shape.
2. Use a common immutable order proposal for both paper and future live adapters:
   exact venue/contract, model and signal timestamp, side/intent, quantity,
   tick-rounded worst acceptable limit, time in force, risk checks, reason and
   strategy version. Archive that proposal before simulated execution.
3. Freeze proposals before a configurable delay. Fetch a subsequent observed
   book and fill only visible eligible levels within the frozen limit. Enforce
   available size, cap participation, simulate partial/unfilled/rejected orders,
   avoid reusing the same liquidity repeatedly, and retain all timestamps.
   Do not grant fills at the signal's earlier quote or invented 50-cent prices.
4. Verify the current venue fee schedule/formula, tick sizes and quantity minimums.
   If account-specific costs cannot be known, explicitly label fee scenarios;
   don't call them actual exchange fees. Report gross and net separately.
5. Start a new forward ledger. Keep Champion and Challenger comparison wallets
   separate, with the same execution model and budgets. Cover each market only
   when its own signal, target, mapping and book pass. Report missing markets.
6. Track realized P/L from official settlements and separately bid-marked open
   positions; preserve raw books, proposals, fill details, rejections and skips.
   Capital is reserved once; settlement is exactly once across restarts.
7. Test expiry, delayed/out-of-order data, outages/429, partial depth, gaps,
   cancellations, rounding, fees, conflicts and recovery before activation.

The bot cannot observe queue position, other traders' intervening orders or an
actual exchange acceptance without real submission. Paper outcomes will remain
estimates. Future live release must reconcile acknowledgements, partial fills,
rejections, balances and positions and requires explicit user authorization;
paper performance must never enable it automatically.

Coinbase already uses sampled real bid/ask data with assumed fees/slippage. Its
next realism pass also needs shared order proposals, depth-limited post-delay
fills, verified fee assumptions and reconnect/gap handling. The public raw
recorder currently has no validated Level-2 book. This Polymarket diagnostic does
not change CBot or pretend to fix Coinbase book reconstruction.

## Offline primitives and accounting update

`trading_bot/execution_model.py` defines the shared order instruction and a pure
post-delay taker-depth simulator. It is not wired to production or a live client.
Its only fee rule is a synthetic reviewed-flat-rate test interface, not the
Polymarket crypto fee formula. Unknown rules are rejected, not approximated.
The caller still needs persistent reservation/order-ID accounting and data
validation before using it. A 25% visible-size participation cap is a modeling
assumption, not a guarantee of exchange fills.

`deploy/update-pbot-market-report.sh --apply` publishes complete-history
per-market accounting and the explicit migration pause message. It does NOT
activate this simulator. No market P/L is silently reclassified as realistic.
