# Uniform crypto tracker pages

BTC, ETH, XRP and SOL have 5m and 15m workspace routes. Each uses its own
Polymarket US event slug, exact typed contract asset/window, verified USD target,
Kraken USD pair and completed candles. A BTC contract can never supply an ETH,
XRP or SOL forecast target. The existing BTC 15m application and Champion
strategy are unchanged; other workspaces now follow its presentation structure.

## Layout

- Matching 348px countdown and candlestick panels in the first row.
- Five-stage live countdown, official target and window times.
- Current asset lean, research position suggestion and next-window preflight.
- Final-target research ABOVE/BELOW percentages and proxy-to-target gap.
- Trading, Performance and Advanced tabs with candle CSV export.

The countdown refers to the fixed selected UTC market window, which must match
contract terms before its target can be shown. Unconfirmed contracts are labeled.
Browser elapsed time is anchored to the server observation with a monotonic
clock; the client wall clock cannot move it into a different window. At the
boundary it shows CLOSED and requests a data refresh rather than rolling over
with a stale target. The existing 60-second automatic app refresh discovers the
next window; the timer does not change the contract data itself.

## Signals and predictions

Each workspace computes five BTC-style momentum votes from its own completed
candles (EMA spread, EMA slope, 3m return, RSI relative to 50, RSI change).
A ±2 net score gives an experimental UP/DOWN lean. Reversal watch highlights
opposing momentum/RSI and EMA direction. Preflight opens during the last three
minutes of the selected market. It describes proxy momentum, not a verified
forecast of the next contract's winner or target.

The final-target baseline is a zero-drift lognormal spot estimate, using that
asset's recent one-minute log-return standard deviation, remaining time and
verified target. It is explicitly uncalibrated. It does not import BTC model
probabilities, BTC historical accuracy or BTC settlement results.

At least 50 completed, consecutive one-minute candles are required. Estimates
pause for stale/future data, interior gaps, missing targets and closed windows.
Lean can remain available when the official target is pending. Permanent history,
verified performance, cloud storage, executable odds and trades are not added.
The Performance tab explains that history is pending rather than inventing it.
Gold/silver show NOT LISTED instead of a market countdown for unsupported 5m routes and their separate futures proxy feed.

## Validation

```sh
python3 -m unittest discover -s tools -v
# Install the existing website requirements to use the Streamlit smoke runner:
python3 tools/smoke_tracker_ui.py
```

29 unit tests pass, including six new signal/target/countdown tests. The pinned
Streamlit 1.51.0 AppTest smoke run passed twelve asset/timeframe shared-workspace
renders, interval switches, complementary forecast outputs, tab layout and a
wrong-asset rejection case. BTC 15m is tested in that runner as a shared-workspace
configuration; the production app continues to route it through its original
page. These fixture tests do not execute iframe JavaScript in a real browser or
prove live contract API availability.

No app.py changes, production database writes, DigitalOcean service changes or
live trades are part of this change. The user has authorized publishing the site
update through GitHub main. Live verification of btc.shaneathon.com is blocked by
the session network policy; pushing main does not by itself prove the hosting
service deployed it. Cloud storage is intentionally deferred.
