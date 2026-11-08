# Polymarket market-band experiment

Version OBSERVED_PAPER_V5_MARKET_BAND. All eight crypto streams remain active and
collecting; the $1.50 entry cap and real-order interlocks remain unchanged.

Entry schedule: wait the first90 seconds. Stop new15m entries with180 seconds
or less remaining; stop new5m entries with120 seconds or less remaining. This
replaces the earlier late-reversal exception. Existing positions can still exit.

Use the official current mark from marketData.stats.currentPx, confirmed in the
user's saved order-book response. Require USD, a finite value in[0,1], reviewed
UP/LONG mapping, and a mark inside the fresh book's bid/ask. DOWN is1-UP.
No model forecast, last-trade price, invented midpoint or ask fallback. Website
rounding may differ from the unrounded API value.

The favored side must be inclusively54–64% and match a fresh same-contract
research lean_direction. Match asset, duration, official target, publication,
completed-candle source and packet timestamps. Neutral/stale/missing/opposite
lean blocks entry. The existing research model supplies the market-local lean.
Own-model forecasts are still recorded/required as fresh feed context, but their
numeric probabilities no longer choose the side or create a model edge.
BTC comparison wallets may therefore behave similarly; this is an execution
experiment, not a pure Champion-vs-Challenger forecasting comparison.

Executable ask limit cannot exceed64c. Reject spreads wider than2 points.
Keep existing fee-inclusive reservations, whole contracts, cash/drawdown/loss
limits, quote identity/freshness, participation and execution delay. Recheck the
mark/lean/window before simulated execution. Actual network latency can move
a live market after a final check; no live-fill or profit guarantee is made.

Maximum5 filled entries per(asset,duration) stream in rolling900s across all
comparison wallets. Partial buys count once; pending proposals reserve slots;
unfilled attempts release them. Recent prior-policy fills also count during
migration. One open/pending position per wallet and15s retry spacing remain.

At actual simulated entry persist the held side's market mark. Freeze the stop
at entry minus0.02 and target at0.71. A55% entry stops at53%, even after a rise
to70%: it is not trailing. Touching either level latches an exit attempt.
No fresh mark means no new trigger; an already latched trigger can keep retrying
against valid bids even if a later mark is missing.

Monitoring uses sampled REST requests under existing budgets/cooldowns, not a
resting exchange stop. Exit fills use fresh liquidation bids, one-tick slippage
limit, minimum2s delay,25% visible participation, full-position FOK and modeled
sell fees. Insufficient depth or price movement can leave an exit unfilled.
The two-point mark trigger is not a2% monetary loss cap;71% is not a guaranteed
sale price/profit after spread and fees. Official settlement remains fallback.

Earlier open positions keep their original V4 model-probability trailing rule
until closed. No entry mark is fabricated for them. Entry-only stop files and
wallet pauses do not prevent exits/settlements. Exactly-once financial accounting,
entry/exit fee reporting, $1.50 cap and all cash/history remain intact.

Deployment: deploy/configure-pbot-market-band.sh --apply. Tests run first.
Back up ledger, temporarily pause new entries, migrate known settings strictly,
cancel unfilled old buy proposals fee-free, switch to band_runner and update
PBot status/UI/hourly/input/health sources. Restore prior units/settings on
failure without overwriting financial history. Already-current policy is a no-op.
Collectors and Coinbase stay running. Existing manual/automatic pauses persist.

Dashboard defaults to a new V5 performance cohort. Actual cash stays all-history.
Market mark, fixed stop, target and trigger times are visible; old results remain.
The hourly guard follows the new cohort. No live keys or paid services added.
