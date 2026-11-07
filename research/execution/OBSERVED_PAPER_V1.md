# Observed-price paper release V1

**Paper only. No exchange keys, account connection or live submission.**
The user authorized paper experimentation and asked for results closer to live
execution. Both old histories are preserved, never imported as new profits.
Deploy once using `deploy/activate-observed-paper.sh --apply`. It creates new
`/var/lib/pbot/observed-v1.sqlite` and `/var/lib/cbot/observed-v1.sqlite`, rejects
existing destination ledgers, updates only bot services and the read-only health
job, and verifies mode/freshness/live-disabled flags. Existing collectors, quote
sampler, backups, recorder, DNS, private tokens and original predictions remain.
If startup readiness fails, prior units are restored; new ledgers remain for
inspection. Do not reinstall over them or reset wallets to hide failed results.

## PBot

Twelve independent $1,000 wallets: original Champion and Challenger B BTC15m
controls plus ten market-specific baseline wallets. They are comparisons, not
one pooled account. Controls require both fresh predictions for the same window.
No new challenger model is added to the other markets. All entries are forward
only, in the final 90–30 seconds, with fresh published/observed signals. Legacy
BTC control feature timestamps are unavailable and explicitly flagged; they are
not invented. The baseline remains exploratory, not statistically validated.

A public REST book is requested for the exact contract, its state/identity/USD
prices/quantities validated, and the original typed asset/window/target matched.
Up/Down mapping uses the explicit Up-if-greater-or-equal rule template, Yes LONG
and No SHORT identifiers, and at least three distinct resolved contracts in the
same asset/horizon cohort including both UP and DOWN outcomes, with no conflict.
This is a documented reviewed template plus outcome corroboration, not a claim
that Yes/No text alone establishes semantics. Unsupported shapes stay paused.
SHORT purchase is modeled as the complementary binary claim: 1 minus LONG bid,
consuming its quantity. It is not leveraged spot shorting or borrowed shares.

The immutable plan records model, signal and first-available timestamps, exact
contract, direction/intent, whole-share quantity, limit/tick, minimum delay,
expiry/TIF, fee basis and mapping evidence. Cash is reserved before an order is
eligible. Limits allow at most one cent worse than the observed ask, rounded
down to the actual tick. Risk: at most $10 cost and one open/pending position per
wallet, $100 daily realized-loss budget including worst-case open commitments,
and 10% realized/cost-basis drawdown halt. Minimum net forecast edge is 3 cents.
Fee rounding allowances are reserved; no fill may exceed reserved cash.

After at least two seconds, a subsequent HTTP book request is required. Frozen
IOC instructions consume at most 25% of each displayed eligible level within
the frozen limit, possibly partially filled; the remainder is cancelled. A
proposal expires after 15 seconds. No queue/maker fills, no favorable fills from
an earlier quote, no 50-cent fallback. Poll scheduling and rate limits can
produce longer latency or no fill. Public GETs are spaced three seconds,
429 respects persistent cooldown, and history storage pauses new quote capture
at 1GiB ledger+WAL or less than 4GiB free disk; settlement processing continues.

HTTP request/response duration, response Date and Age establish snapshot
freshness; `transactTime` is retained as the last book transaction time and may
be old on an unchanged book. This is not a validated continuous websocket book.
Books, raw metadata, mapping proof, plans, fills, skips and official settlement
accounting are retained. State transitions and payouts are exactly once across
restarts. Conflicting target/identity/finality never pays a position.

Fee basis: user-relayed support says published taker coefficient **0.06**,
`c*q*p*(1-p)`, nearest-cent HALF_EVEN per execution. Maker rebates are never
credited for taker orders. The observed market coefficient **0.095** is not
silently substituted or discarded: each position stores that field and the
fee sensitivity at the API coefficient. Actual override applicability remains
unconfirmed. Aggregated books hide individual counterparty executions: one
simulated execution per consumed price level is an explicit assumption, and
actual per-fill rounding may differ. Do not describe these costs as reconciled
actual exchange fees or the P/L as guaranteed live profit.

Settlements use already-verified official results. Primary P/L is realized;
open cost and reservations are separate, not marked liquidation equity.
Per-market gross/fees/net totals use the complete ledger, not the displayed
latest-position subset. Use `/var/lib/pbot/STOP-OBSERVED` to cancel queued
proposals/stop new ones while continuing verified settlements.

## CBot

A new shared $1,000 spot wallet covers BTC/ETH/XRP/SOL USD, using the same
existing EMA/return entry and stop/take-profit/trend-exit strategy. It retains
its position/exposure/daily-loss/drawdown controls. Old virtual positions and
history remain archived in `paper.sqlite`; they are not transferred or sold
into the new wallet. No actual funds or positions exist in these ledgers.

A durable frozen `limit_limit_fok` instruction (the Coinbase SDK supports this
configuration) records product, side, client ID, base quantity and price limit,
with actual product increments/minimums. Buy and sell proposals wait at least
two seconds for a *later* sampled book and expire after 45 seconds. Actual wait
follows the collector's cadence, not an invented two-second quote. Buy size is
capped initially and on arrival at 25% of displayed best ask size; sells require
the entire frozen quantity fit within 25% of bid size. Limit/depth failure
produces an unfilled FOK, without fees. No passive fills or partial FOKs are
invented. Cash reserved for other products cannot be spent twice. Exits remain
available during an entry pause; new BUY proposals are cancelled by the pause.

Fills use actual observed bid/ask, with the old 5bps slippage parameter serving
as the limit allowance rather than an automatic price markup. **0.6% per side
remains an explicit fee estimate** until actual account tier and precision are
available. No claim of exact account fees or reconstructed Level-2 is made.
Per-product gross, estimated fees and net P/L are shown; permanent orders and
trade journals support review, and API histories are bounded. A stopped,
restricted, stale, crossed or otherwise invalid product cannot supply a fill.
The collector's status API supplies samples without extra exchange requests.
Use existing `/var/lib/cbot/STOP` to stop new entries; exits continue.

## Shared future live boundary

`trading_bot.live.observed_order(plan)` and
`coinbase_bot.live.observed_order(proposal)` expose the same frozen instructions
used by the simulators. Both live submission functions still raise disabled
errors. A future live implementation must add actual exchange authentication,
acceptance/partial-fill/rejection reconciliation, balances, cancellation and
recovery—not assume the simulated response. Enabling it requires separate,
explicit user authorization. Two profitable days do not validate a live edge.
