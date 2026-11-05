# BTCandThings read-only research audit

This audit is intentionally **separate from the live collector and dashboard**.
It only performs HTTPS GET requests to Supabase; it does not trade, backfill,
change settlement results, or write database rows.

## Run (when read-only credentials are available)

Set `SUPABASE_URL` and `SUPABASE_KEY` as **environment variables** using a
least-privilege, SELECT-only credential. Never commit keys to GitHub.

```bash
python3 tools/research_report.py --out btc_performance_report.json
python3 -m unittest discover -s tools -p 'test_research_report.py'
```

The report evaluates **one earliest valid prediction per verified BTC market**,
plus model-version, probability-calibration, and 3/5-minute forecast summaries.
It reports sample coverage and a Wilson confidence interval. Multiple refreshes
of the same market are not counted as independent successes.

This is **not** a live profitability report. Quote availability alone is not
proof of executable prices. Realistic paper trading requires time-aligned entry
and exit quotes, spread, fees, slippage, and a frozen trading rule. Six-asset
performance is **not** covered by the current BTC-specific tables.

If the lean forecast table is not yet deployed, the script reports that limitation.
No secrets or market data are copied into GitHub by this change.
