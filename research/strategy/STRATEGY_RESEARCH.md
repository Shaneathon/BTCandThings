# Strategy research: Polymarket US and Coinbase spot

November 6, 2026. All recommendations below are for independently versioned
paper experiments. Existing production Champion calculations stay unchanged.

## 1. What we know from this project

The paired Bitcoin audit used verified official outcomes, one prediction per
market/model/checkpoint, and predictions recorded no later than the checkpoint,
up to 90 seconds old. On 95 common BTC 15m markets at the one-minute checkpoint:

| Model | Accuracy | Brier loss |
| --- | ---: | ---: |
| Pixel V13.5 Headless Baseline | 85.26% | 0.076653 |
| Challenger A Momentum V1 | 90.53% | 0.057080 |
| Challenger B Volatility V1 | 95.79% | 0.043467 |
| Challenger C Momentum Volume V1 | 92.63% | 0.043846 |

For the later 48 markets, B remained ahead of Champion: 93.75% versus 81.25%
accuracy and Brier 0.050301 versus 0.082757. This later segment was inspected
after the fact; it is not a newly untouched holdout. Ninety-five adjacent
markets do not equal ninety-five independent market regimes. Historical
`recorded_at` may be a candle boundary rather than actual publication time;
availability and ingestion timestamps need separate verification.

The generic BTC 15m research baseline at ten minutes remaining had only 42
markets and Brier 0.257948, worse than a constant 50% forecast's 0.25. That says
little about the original Champion, and does not justify suppressing all early
signals across different models or assets. The BTC 5m baseline near expiry
also looked stronger than earlier forecasts, but it is a separate experiment.

**Conclusion from observed data:** prioritize B, retain C as a later comparator,
and test horizons separately. Do not promote B to production or extrapolate
Bitcoin's results to ETH, XRP, SOL, gold or silver yet.

## 2. Prediction accuracy and entry value are different problems

A binary contract paying $1 has expected net profit per share:

`EV = probability_of_correct_side - executable_entry_price - per_share_costs`.

Example, not a measured market: a calibrated 95% chance of winning at a 98c ask
with 2c total costs has EV -5c/share. A high win rate can lose money. A 60% win
probability at 50c plus 2c costs has EV +8c under those assumptions, but only if
the probability, quote mapping, liquidity and costs are real and time-aligned.

At fixed 50c reference plus 1c slippage and 1c fee, the current PBot sandbox
costs 52c/share and needs a long-run success rate above 52% to break even before
other modeled effects. Its apparent profitability is largely built into that
artificial price. It is useful for comparing directions under matched rules,
not proving an exploitable trade. Keep this ledger distinct from future
quote-based ledgers; never merge synthetic and executable-price results.

Evaluate the complete funnel: eligible opportunities, fresh signals, available
quotes, qualified entries, attempted simulated orders, modeled fills, partial
fills, exits, final settlements and net results. A strategy with few fills may
look excellent on filled trades while being unusable as a complete portfolio.

## 3. Use the correct Polymarket venue and settlement instrument

This project uses **Polymarket US**, not an interchangeable global CLOB. Its
event slug/contract mapping, APIs, authentication, order intents, market types,
fees and settlement definitions must be checked in their own right. Do not
copy global Polymarket fee schedules or assume the same 5m contract identifiers.

Observed user-supplied BTC/ETH contract descriptions specify official CF
Benchmarks indices and averages of 60 samples in the last minute before the
start/end timestamps. ETH's supplied description explicitly resolves equality
to UP. Verify the relevant description, symbol, time window and rounding for
each contract; do not assume every asset uses the same index or decimals.
Gold/silver references differ and currently lack a reliable proxy feed.

The existing spot model estimates a terminal spot distribution. The actual
contract may settle on an average of official index samples. These are not the
same target, particularly in the final minute. Candidate features:

- Official price-to-beat, explicit settlement index, rounding and tie rule.
- Number of official settlement-window samples already known, their sum and
  mean, and the uncertainty in the remaining samples.
- Official-index versus Kraken/Coinbase spot basis and the age of each source.
- Remaining time, normalized distance to target, volatility and jump flags.

For a simple level random walk, the unknown samples share correlated future
increments. If `m` one-second samples remain, per-second increment variance is
`s²`, and the contract averages `N` total samples, the remaining average's
innovation variance is `s² * sum(k² for k=1..m) / N²`, not independent-sample
variance `m*s²/N²`. This is a modeling illustration, not an approved model:
real index dynamics, rounding, gaps and jumps require validation. Before the
averaging window starts, uncertainty in the future window's starting level
must also be modeled.

Do not reconstruct official samples from arbitrary proxy ticks and call them
official. A proxy-only version can be tested separately with an explicit basis
uncertainty term and must fail closed when that basis is unmeasured.

## 4. Polymarket candidates in priority order

| Candidate | Entry idea | Why plausible | Failure mode / required test |
| --- | --- | --- | --- |
| Champion vs B, fixed-price baseline | Existing final 90–30s directional experiment | Local matched-data advantage for B | Artificial prices; cannot rank realizable profits |
| B with executable-value gate | Enter only when conservative calibrated probability exceeds mapped ask plus costs | Converts forecasts into a price-sensitive decision | Poor calibration, stale asks, index/proxy basis, adverse selection |
| Averaging-window model | Predict remaining official settlement average | Targets actual payout mechanism | Official feed unavailable; correlated samples and rounding mishandled |
| Horizon-specific calibration | Separate probabilities by 5m/15m and remaining-time bucket | Local results differ strongly by horizon | Too many thin buckets; future leakage when fitting |
| B with target-distance/volatility filter | Require stable evidence rather than a bare UP/DOWN label | Can exclude ambiguous target crossings and extreme regimes | Selecting only easy late events at uneconomic prices |
| Trend versus reversal regimes | Compare momentum and mean reversion in prespecified conditions | Market behavior may vary by regime | Hindsight regime labels, many parameter trials, fees |
| Book/flow confirmation | Use imbalance and signed executed volume as secondary features | May describe short-lived pressure | Spoofable displayed size, wrong aggressor-side semantics, latency |
| Early exit versus settlement | Compare net bid exit with holding the same position to payout | Can reduce tail exposure or release capital | Round-trip spread/fees eliminate benefit; need actual bid/depth |
| Maker-only research | Model resting orders and queue priority | Potential spread capture | Touch is not a fill; queue position and cancellations are unknown |

Do not immediately combine all filters. Compare one change to a frozen
baseline first. Order-flow features should be tested for incremental value
after price, volatility, target distance and time are already accounted for.

Useful deterministic entry checks before any realistic simulated fill:

1. Exact event and linked contract; typed asset/window/target match.
2. Verified semantic direction-to-exchange-side mapping for that contract.
3. A quote observed after the signal became available and before the order
   decision, and a separate quote at modeled order-arrival time.
4. Nonmissing, noncrossed prices; sufficient depth at the chosen size; valid
   price/quantity increments and minimum trade quantity.
5. Expected edge after fees, spread, slippage and probability uncertainty.
6. Time until closure, source freshness, reconnect/gap state and rate budget.
7. Per-trade, per-asset, correlated-portfolio, daily-loss and drawdown budgets.

Use a conservative probability bound or explicit uncertainty buffer rather
than trusting an uncalibrated 95% label as precise. Avoid buying probability
extremes solely because the directional hit rate is high. Keep abstention a
legitimate outcome and record the skipped reason.

## 5. Polymarket exits and paper fill realism

Holding to a verified settlement pays by the contract winner. Selling early
requires executable bids, side mapping, price/size increments, costs and a
specific fill model. Compare both on the same entry cohort; do not backfill a
better exit chosen after seeing the final outcome.

A resting limit order needs a queue model. A later trade at the limit price
does not prove our order would fill. A market order needs a depth walk and
arrival-time quote; do not assume all requested shares fill at best ask. If
depth is incomplete, report a censored/unfilled opportunity or a conservative
size limit, not unlimited synthetic liquidity. Model partial fills and track
exposure reserved for pending simulated orders.

The US SDK confirms `marketData` envelopes, nullable BBO prices, a book endpoint,
and a settlement endpoint with a numeric result. A numeric settlement by
itself does not prove UP/DOWN meaning. The inspected WebSocket base signs
connections using credentials; inspect read-only access/scopes before adding
an authenticated streaming connection. Do not introduce trading credentials
or import the live order path to obtain paper data. [S1–S4]

## 6. Coinbase spot: current baseline and the cost hurdle

CBot currently compares EMA9 and EMA21 on completed one-minute closes and the
three-minute return. Positive alignment can trigger a simulated long entry;
negative alignment can trigger a trend exit. It also checks fresh books,
spread, depth, product increments, exposure and loss budgets. It is long/cash,
not a shorting, futures or leveraged strategy.

Current assumed costs are 0.6% fees and 0.05% slippage per side. These are
configuration assumptions, not the user's verified fee tier. Ignoring spread,
an exit bid needs to exceed the entry ask by approximately **1.31%** just to
break even under those costs. Sampled bid/ask spread is an additional hurdle
when expressing the move relative to a common midprice. Small minute-scale
signals can be overwhelmed by this cost; more trades are not automatically
better. `costs.py` computes the exact hurdle for supplied assumptions.

Current 2% stop/4% target values are measured from the simulated entry price,
not net-of-fee returns. Their true risk/reward differs after exit fees, spread
and slippage. A stop checked once per minute is not guaranteed to execute at
the threshold; gap-through exits must use a later observed executable price.

## 7. Coinbase strategy families to paper-test

| Candidate | Prespecified test | Main reason to consider it | Common failure |
| --- | --- | --- | --- |
| Unchanged EMA baseline | Current rules and cost model | Honest benchmark and source of operational observations | Churn, lag and insufficient move after costs |
| Cost-aware momentum | Require a separately validated move/return forecast to exceed costs | Avoids trades with an uneconomic horizon | A volatility estimate is not a directional expected-return forecast |
| Slower trend confirmation | Compare 5m/15m features with the 1m baseline | Lower turnover may reduce costs | Delayed exits and reversal losses |
| Volatility breakout | Break a range computed only from earlier candles; require volume confirmation | Tests persistent moves after compression | False breakouts, gaps, worse fills and volatility clustering |
| Range mean reversion | VWAP/deviation or band reversal only in prespecified nontrending regimes | Tests a different mechanism from momentum | Buying a persistent decline; regime hindsight |
| Pullback within trend | Enter after a defined pullback while a higher-timeframe trend remains positive | Tests entry price improvement versus chasing | Missed winners; delayed confirmation cannot use a future candle |
| Volatility-adjusted sizing/exits | Compare ATR-scaled paper exposure and exits to fixed percentages | Normalizes risk across BTC/XRP/SOL and regimes | Backtest intrabar assumptions, unstable ATR and minimum-size constraints |
| Liquidity/flow filter | Reject wide/thin books; test incremental imbalance or trade-flow features | Potentially avoids expensive and adverse entries | Quote size disappears; trade side may not mean aggressor side |
| Time stop/cooldown | Exit or pause after a predeclared duration or repeated loss pattern | Limits capital trapped in weak trends and overtrading | Excluding a recovery based on hindsight; rule overfitting |
| Cross-asset context | BTC trend/volatility as a feature for ETH/XRP/SOL | Tests shared market factors | Correlation shifts, redundant bets and synchronized losses |

Use buy-and-hold, cash and unchanged CBot as explicit comparators. Measure
turnover, exposure-time and costs, not only terminal USD profit. A bot that
holds little crypto may underperform in a bull market yet have lower risk;
report both facts. Keep product-specific results and combined correlated
portfolio results. Do not extrapolate a BTC-only optimum to every coin.

Derivatives funding, open interest and liquidation data can be context, not
permission to trade derivatives. Calendar/news features need publication-time
archives, point-in-time revisions and a documented source. They are later
experiments, not prerequisites for establishing a sound spot baseline.

## 8. Calibration and statistical testing

Use reliability diagrams with counts and uncertainty, Brier loss and log loss.
Brier combines calibration and discrimination/refinement; lower Brier does
not by itself prove better calibration. Report class balance, a constant 50%
forecast and an appropriate training-only base-rate forecast. [S8]

For small samples, first investigate coarse reliability bins or simple
logistic/sigmoid calibration trained strictly on past data. Flexible isotonic
calibration can overfit; the inspected scikit-learn reference discusses a
roughly 1,000-sample regime, not a universal guarantee. Repeated predictions
within one market are not independent samples. Avoid separate calibrators for
every coin, stage, weekday and volatility bucket before the sample supports it.

Use rolling or expanding chronological training windows. A training label is
available only after that market settled and the result was received. Purge
training examples whose label intervals overlap the test period; a simple
random train/test split or a nominal time gap alone may not prevent leakage.
Five-minute and fifteen-minute windows for the same underlying overlap and
must be grouped appropriately. Ordinary time-series splitting is a starting
point, not a complete financial backtest design. [S9, S10]

After selecting a candidate on earlier data, freeze it and evaluate genuinely
new markets. Day/week-block uncertainty estimates are preferable to treating
every adjacent trade as independent. Count all attempted parameterizations,
including discarded ones, to expose multiple-testing risk. Reserve a final
untouched segment and do not repeatedly tune against it. If examined, it is no
longer untouched. Use more than one volatility/trend/news regime.

## 9. Execution and experiment accounting

Log exchange/source time, receipt time, parse time, candle-close time, feature
cutoff, signal-available time, decision time, modeled order-arrival time,
quote age, fill time and settlement receipt. Use UTC timestamps plus monotonic
durations where suitable; observe clock offset rather than rewriting history.
Use Decimal prices/quantities and contract/product increments in accounting.

Market replay must model latency, cancel/replace delays, depth and queue
position when relevant. Paper results from candle high/low are not evidence
of intrabar execution. High and low do not establish which threshold occurred
first. Use higher-resolution data or conservative adverse ordering when both
stop and take-profit were touched. Backtesting tools document substantial fill
assumptions; hftbacktest explicitly emphasizes latency and queue modeling.
These engineering references justify caution, not an endorsement of their
example strategies. [S10–S12]

Every run needs immutable strategy/configuration hashes, source versions,
dataset cutoff, fill-model version, fee assumptions, universe and ledger ID.
Compare paired opportunities, but report each strategy's own coverage and
skip/fill rates too. Realized P/L, unrealized marked equity, max drawdown,
tail loss, turnover, capital usage, win/loss sizes, profit factor and exposure
concentration all matter. Define behavior when no trades or no losses occur;
do not print infinite profit factor as evidence of a proven strategy.

## 10. Autonomous improvement without rewriting the baseline

The user authorizes autonomous paper changes. The implementation should:

1. Classify operational faults first: stale signal, wrong product/contract,
   missing mapping, mismatched timestamps, duplicate entry, incorrect fees,
   or incorrect settlement/accounting.
2. Treat a valid losing prediction as an observation, not automatically a bad
   decision. A calibrated 80% forecast should sometimes lose.
3. Propose one falsifiable change with a plausible mechanism. Record what
   evidence would reject it before running it.
4. Start a new independent experiment with the same opportunity clock and
   risk/cost assumptions; never rewrite prior ledger entries.
5. Promote only after better forward net results and risk across multiple
   periods, with uncertainty and operational behavior acceptable. Demote or
   pause after prespecified deterioration/data-quality rules.
6. Keep real-order submission disabled. Paper success never toggles live mode.

Automatic loss labeling is already in the PBot sandbox; automatic strategy
optimization/deployment is not. A scheduler/reviewer must be separately built
and tested before claiming unattended self-improvement. Avoid a bot that
changes parameters after each loss; that often learns noise and destroys the
comparison. A review report can run daily while promotion requires enough new
independent evidence, not merely the passage of a day.

## 11. Recommended first experiment sequence

1. Preserve the existing PBot two-model directional baseline and CBot baseline.
2. Complete data quality and quote realism before selecting by paper P/L.
3. Polymarket: B versus Champion at the existing checkpoint under *mapped real
   quote* simulation; start with BTC 15m, expand only on verified inputs.
4. Coinbase: cost sensitivity and turnover/holding-time analysis, then one
   slower trend variant; compare against unchanged CBot on all four products.
5. Test settlement-average modeling and simple calibration once official
   input availability and enough independent markets support them.
6. Evaluate breakout, mean reversion and flow as distinct candidates, not one
   giant optimized rule. Keep unsupported markets visibly paused.

Suggested screening checkpoints: at least 200 new settled markets over at
least 14 days for a binary candidate, and at least 100 completed spot trades
over multiple regimes for a spot candidate. These are planning floors, **not
statistical sufficiency guarantees**; sparse trading or high dependence may
require much more data. Predefine acceptance and rejection rules per test.

## Sources actually read

- **S1** [Official Polymarket US Python SDK](https://github.com/Polymarket/polymarket-us-python), inspected commit `6fde8f2b6ea88198a199b38f7b6d8951d015a06a`.
- **S2** [US market resource](https://github.com/Polymarket/polymarket-us-python/blob/6fde8f2b6ea88198a199b38f7b6d8951d015a06a/polymarket_us/resources/markets.py).
- **S3** [US market types](https://github.com/Polymarket/polymarket-us-python/blob/6fde8f2b6ea88198a199b38f7b6d8951d015a06a/polymarket_us/types/markets.py).
- **S4** [US WebSocket authentication implementation](https://github.com/Polymarket/polymarket-us-python/blob/6fde8f2b6ea88198a199b38f7b6d8951d015a06a/polymarket_us/websocket/base.py).
- **S5** [Official Coinbase Advanced Python SDK](https://github.com/coinbase/coinbase-advanced-py), README including public REST/WebSocket examples.
- **S6** [Coinbase public REST resource](https://github.com/coinbase/coinbase-advanced-py/blob/master/coinbase/rest/public.py).
- **S7** [Coinbase WebSocket channels](https://github.com/coinbase/coinbase-advanced-py/blob/master/coinbase/websocket/channels.py) and response types; availability/sequence semantics must still be checked against live messages.
- **S8** [scikit-learn probability calibration](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/calibration.rst).
- **S9** [scikit-learn time-series cross-validation](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/cross_validation.rst).
- **S10** [Freqtrade lookahead analysis](https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md).
- **S11** [Freqtrade backtesting assumptions](https://github.com/freqtrade/freqtrade/blob/develop/docs/backtesting.md).
- **S12** [hftbacktest](https://github.com/nkaz001/hftbacktest), engineering reference on depth, latency and queue simulation.
- **S13** [Avellaneda–Stoikov community implementation](https://github.com/fedecaccia/avellaneda-stoikov), inspected README only; a secondary implementation, not proof of crypto applicability or profitability.

`sources.json` records successful/failed retrievals and SHA-256 hashes. SDK
methods are technical evidence, not a verified current fee schedule. The
settlement descriptions and paired results above came from the user's actual
public-market records and generated audit, not from inaccessible web pages.

Further literature to obtain and critically review: Avellaneda & Stoikov on
inventory-aware market making; Cont, Kukanov & Stoikov on order-book-event price
impact; Gneiting & Raftery on proper scoring rules; Bailey and coauthors on
backtest overfitting; and peer-reviewed crypto momentum/reversal studies. Their
full papers were not retrieved in this environment, so no new claim here is
presented as a conclusion from reading those originals.
