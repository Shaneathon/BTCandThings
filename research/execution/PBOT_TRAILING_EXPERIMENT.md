# All-market, full-window paper entry and probability-trailing experiment

The user's final choice supersedes the proposed BTC15-only restriction: keep all
8 crypto streams trading (BTC/ETH/XRP/SOL × 5m/15m), with the BTC15 Champion,
Challenger B and research comparison wallets retained. Source collection stays
unchanged. Real submissions remain disabled. Version: OBSERVED_PAPER_V4_TRAILING_150.

## Entries

- $1.50 maximum total entry spend including modeled entry fees; whole contracts,
  price improvement and partial fills may spend less. Existing minimum intended
  order cost remains $0.50. No capital resets or larger tickets.
- Examine opportunities throughout the selected market's own window. Exact
  current official target/contract, fresh signals/input and reviewed book mapping
  remain mandatory. Freshness thresholds are not relaxed.
- With 120 seconds or less remaining, a fresh model forecast (at most30s old)
  must show >=65% confidence in the chosen side, after an actually observed
  opposite-direction >=65% forecast in the same contract during the prior120s.
  Modeled net edge must be at least10 percentage points. This is a model reversal
  definition, not verified price-action reversal or demonstrated profitability.
  Earlier entries retain3-point minimum modeled edge. Both include entry fee
  estimates and a conservative2-cent/share exit-fee allowance. Actual exit costs
  and returns are unknown when entering. No new entries in the final15seconds;
  delayed fills crossing into the late period are rechecked.
- Maximum3 filled entries in a rolling900s per asset/duration stream, combined
  across its comparison wallets. A partially filled buy counts once. Pending buys
  reserve slots, rejected/unfilled orders release them. BTC5m andBTC15m have
  separate budgets. All policies' recent actual fills count during migration.
- One open/pending position per wallet remains. Reentry in the same contract can
  occur after closure, with >=15s between attempts and the rolling quota intact.
  Separate stored entry keys retain the real contract slug in each payload.

## Probability trailing exits

The user chose **our model's probability**, not Polymarket displayed price. For
UP use p(UP); for DOWN use 1-p(UP). Initialize from the saved entry forecast,
ratchet the peak upward with fresh, same-model/same-contract observations, and
latch an exit when the value falls0.05 (5 percentage points) from that peak.
55%→50% or a72% peak→67% trigger.72% is not a fixed profit target. A rising
model probability does not prove the position's market value or P/L increased.
Missing/stale model data never invents a trigger. Once triggered, a bounce does
not cancel the queued stop; retry while there is still time and valid data.

The paper exit uses normalized liquidation bids for the held claim, not buy asks
or model probability as a sale price. Frozen limit, minimum2s delay, fresh
post-arrival request, 25% visible participation, and modeled0.06 quadratic sell
fee rounded by consumed price level apply. Limit is one tick below the observed
best bid. Full-position FOK exits only: insufficient depth or price movement
produces an unfilled, fee-free attempt, not an invented partial sale. A later
attempt can use a new validated book/limit. Near expiry the window may close
before an exit fills; official settlement remains the fallback.

The5-point confidence rule is **not a cap on monetary loss** or a guarantee of
sale/profit. No continuous exchange-orderbook/queue guarantee is asserted.
Manual entry stop files, daily/drawdown limits and hourly entry-only wallet pauses
never prevent exits or official settlement. Existing open positions adopt the
new exit rule using their saved entry forecast. Old entry tags are preserved.

## Accounting and operation

Exits credit net sale proceeds once, charge modeled sell fees, close the exact
entry record and keep entry basis/P&L. Already-closed positions cannot receive a
later settlement payout. Settlement that wins a race with an exit cancels that
exit without proceeds or fees. Entry and exit fees are shown separately, and
realized gross/net accounting reconciles. Repeated entries in the same contract
have distinct order identities. All full-history/page/settlement pinning code
uses the real contract slug, not an internal entry suffix.

The dashboard labels this as a new performance period, retains earlier/all
history, displays model trails and exit orders, and distinguishes entry quota
waits from frozen services. The hourly guard assesses completed trades from this
new entry cohort; existing wallet pauses persist. All original cash/history and
live-order interlocks remain intact.

Deploy with `bash deploy/configure-pbot-trailing.sh --apply` after staging the
research branch. Tests run first; a temporary entry-only STOP protects migration.
It backs up the ledger, migrates only known settings and cancels unfilled old
buy proposals without fees. It updates PBot paper/status/dashboard/hourly review,
input exporter and health source, preserving source collectors/Coinbase. Timers
resume; settings/units roll back on failure without overwriting financial rows.
An already-current configuration is a no-op. Existing manual stops are preserved.
