# Asset × timeframe workspace

A clean two-level selector replaces the always-expanded six-card radar.
The six assets (BTC/ETH/XRP/SOL/Gold/Silver) and two durations (5m/15m)
give twelve selectable views. Existing full BTC 15m analytics are retained
unchanged; the other eleven views show independently verified Polymarket US
contract metadata, official target when available, countdown, and optional
Kraken crypto spot chart. No unvalidated predictions are shown.

**Market availability:** Polymarket US lists BTC/ETH/XRP/SOL 5m and 15m,
and Gold/Silver 15m as of 2026-11-05. Gold/Silver 5m selectors are reserved
and clearly labeled unavailable, not invented as live markets.

**Not yet included:** 24/7 collectors and validated predictive models for
the other eleven asset/timeframe combinations, or execution-quality odds
and trade-performance data. This change does not alter trading or BTC data
collection. All new market data is read-only.

Offline tests: `python -m unittest discover -s tools -p test_market_workspace.py`.
