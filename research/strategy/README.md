# Bot strategy research and expansion plan

Prepared November 6, 2026. Research and paper testing only; live submission
remains disabled. This directory does not deploy or modify a production model.

- [Research guide](STRATEGY_RESEARCH.md): strategy families, evidence, costs,
  entry/exit rules, failure modes and experiment priorities.
- [Collection and rollout](COLLECTION_AND_ROLLOUT.md): missing data, retention,
  source quality, all-market paper readiness and the deployment sequence.
- `sources.json`: sources actually retrieved, URLs, dates and content hashes.
- `experiments.json`: small, versioned candidate list; none is auto-activated.
- `costs.py`: testable hypothetical execution-cost calculations, not an order
  adapter or a fee schedule.

## Current reality

PBot compares Champion V13.5 and Challenger B on forward BTC 15m markets under
**fixed hypothetical 50c reference prices**, 1c slippage and 1c fee per share.
Its P/L is an artificial directional experiment, not evidence of attainable
Polymarket profitability. Verified UP/DOWN-to-exchange-side mapping, executable
quotes and liquidity remain unfinished. Do not silently relabel this experiment.

CBot already runs a four-product Coinbase spot paper wallet using the existing
Coin research feed: BTC-USD, ETH-USD, XRP-USD, SOL-USD. Fills use sampled books,
estimated slippage and assumed fees; no Coinbase order is placed. Its current
rule uses EMA9/EMA21 and a three-minute return, with risk and exit checks.

The user authorizes autonomous paper-only tweaks. Maintain a frozen baseline,
separate ledgers/configuration for each change and a permanent experiment log.
The current bots do not automatically self-optimize or guarantee that a human
assistant is continuously monitoring them. Installed services can collect and
classify observations unattended; additional automation must be explicitly
implemented, tested and deployed before being described as running.

## Research access and evidence labels

Official SDK repositories and validation/backtesting engineering sources were
read directly. Full hosted exchange documentation and academic sites could
not be fetched from this environment. Do not claim current fee tiers, current
regional permissions, official index-feed access or strategy profitability
were verified from those inaccessible sources. Source code is evidence of an
interface, not proof that the user's live endpoint/account supports it.

Claims in the guide distinguish: **observed project data**, **read first-party
SDK**, **engineering reference**, **mathematical consequence**, and **hypothesis
to test**. There is no discovered or promised universally profitable strategy.
