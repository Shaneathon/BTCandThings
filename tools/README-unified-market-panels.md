# Unified 5-minute / 15-minute market tracker panels

The dashboard now uses the same **timer, verified target, candlesticks,
current momentum lean, next-window preflight, final prediction placeholder,
three-stage progress, accuracy placeholder, and diagnostics** layout for
every asset/timeframe selection.

### Data sources (explicitly proxies)
- BTC/ETH/XRP/SOL: Kraken **completed** 1-minute OHLCV spot candles.
- Gold/Silver: optional Yahoo Finance **GC=F / SI=F futures** 1-minute
  candles. These are futures, not spot or Polymarket's Chainlink reference.
  Yahoo data may be delayed, unavailable, or rate-limited. The UI fails
  closed to "pending" rather than fabricating prices.
- Every chart can switch between 1-minute and **fully completed** 5-minute
  candles. Partial current 1m and 5m bars are excluded.
- A price-to-beat is displayed only when the Polymarket US contract's typed
  metadata verifies the exact asset, market type and UTC window.

### Prediction status
Current momentum lean uses five transparent indicator votes (EMA9/EMA21,
price/EMA9, RSI14, 3-minute and 5-minute returns). It is labeled
**experimental, unvalidated, not a win probability**. Stale or insufficient
bars disable it. The next-window panel is context only; the final market
probability, independently verified accuracy, and paper P/L remain PENDING
until dedicated per-market collection and validation are connected.

The existing BTC 15m advanced tracker remains intact. Other workspaces do
not write to the BTC tables or reuse BTC settlement records. Gold/Silver
5m views remain accessible for layout/chart research, but are explicitly
marked unlisted until Polymarket US offers corresponding contracts.

### Tests
```bash
python -m unittest discover -s tools -p 'test_unified_candles.py' -v
```

### Next deployment work
Verify official settlement mappings, choose compliant data feeds for metals,
deploy 5m/15m six-asset collectors with distinct market identifiers, and
backtest each independent model before displaying forecast probabilities or
activating paper trading.
