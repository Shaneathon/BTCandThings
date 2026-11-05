# BTCandThings champion/challenger research — v1

This is a **shadow research tool**, not a replacement for the live prediction
engine. It does not change Streamlit, the DigitalOcean collector, trading, or
database records. It uses the existing Supabase GET-only client in
`tools/research_report.py`.

## What it tests

- **Champion:** archived original `predicted_up_probability`.
- **Challengers:** predeclared mild/strong 3-minute spot momentum shifts and
  mild reversal shift to the incumbent's log-odds.
- **Fairness:** earliest prediction in the first 5 minutes of each **verified**
  BTC 15-minute market; one observation per market, using only spot data at or
  before prediction time. A usable observation approximately 3 minutes earlier
  is required.
- **Selection:** first 60% of eligible markets by time selects one challenger
  using Brier score. Remaining 40% is held out, untouched during selection.
  At least 250 eligible markets and 100 holdout markets are required.
- **Gate:** challenger must beat champion by at least 0.005 Brier points on
  holdout and the paired bootstrap interval for the difference must be
  strictly below zero. This merely makes it **eligible for prospective shadow
  testing**; it never automatically deploys.
- **Limitations:** this is a small fixed candidate family, not machine
  learning; no order book or executable price information, no trading costs,
  no six-asset coverage, no proven edge. Reusing the same holdout across many
  future experiments would invalidate its independence. Create a new
  prospective evaluation period before any live promotion.

## Run

Supply a SELECT-only `SUPABASE_KEY` and `SUPABASE_URL` as environment
variables outside GitHub. Never commit secrets or generated raw data.

```bash
python3 tools/challenger_research.py --out challenger_report.json
python3 -m unittest discover -s tools -p 'test_challenger_research.py' -v
```

If the database has insufficient usable markets, the report explicitly says
`insufficient_data`. **Do not interpret that as evidence of profitability.**
