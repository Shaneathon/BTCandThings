# Proposed Supabase schema for 12 selectable trackers

**This migration has NOT been applied.** It is a ready-to-review database
contract for the next data-collection phase. The existing BTC collector and
`btc_*` tables remain untouched.

- Six assets: BTC, ETH, XRP, SOL, GOLD, SILVER
- Durations: 300 seconds (5m) and 900 seconds (15m)
- Gold/Silver 5m market windows should **not** be inserted until actual
  Polymarket US contracts exist.
- Market windows store only independently verified official targets and
  settlement winners. Numeric 0/1 settlement fields must not be interpreted
  as UP/DOWN without documented side mapping.
- Candles are source-tagged proxy prices, distinct from official settlement.
- Predictions include model version, champion/challenger role and source time.
- Quotes must be time-aligned to a verified contract before paper P/L.
- Paper trades are **simulation-only**, not live orders.
- Tables have row-level security enabled and no public access policies.

## Tomorrow's deployment sequence
1. Review schema and permission model; apply once in Supabase SQL editor.
2. Verify Polymarket US market identifiers and typed terms per asset/duration.
3. Confirm compliant reliable 1m sources, especially metals and 5m markets.
4. Deploy collector support with unique asset+duration windows; run in shadow.
5. Establish verified settlements and score models by independent market.
6. Connect dashboard read-only history and realistic paper trading.

No database credentials, secret tokens, or production writes are included.
