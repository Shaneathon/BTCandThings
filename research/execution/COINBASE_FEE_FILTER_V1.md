# Coinbase fee-filter paper experiment V1

User approved reviewing current results and testing a separate paper version.
Baseline evidence:41 closed trades net -21.9420150438472, gross -0.6842971006,
estimated fees21.2577179432472. Last6h19 trades gross+0.1064983940, fees9.3652330903308,
net-9.2587346963308; all recent exits TREND_EXIT, medianhold13.87min, median
proposal-to-fill20.3s. Fees are estimated0.6% per side, not actual account fees.
This shows cost drag/churn, not proof of a profitable alternative.

Hypothesis: an entry-only regime filter can reduce low-movement trades whose
price changes are too small for costs. No parameters were optimized against
individual historical fills. V1 is fixed before forward testing:

- Keep baseline EMA9/21 and3m return BUY signal.
- Require observed15m return >=0.3%, EMA9/EMA21 separation >=0.1%.
- Require last60 completed1m bars' high-low range /lastclose to exceed
  fee-only break-even ((1+fee)/(1-fee)-1), plus twice current relative spread,
  twice the0.05% limit allowance, and a0.3% buffer.

**Observed range is not a forecast of future profit or a calibrated expected
return.** The hypothesis may fail, select reversals, or generate no entries.
Range/return/separation and the threshold are recorded in signal/decision data.
Filtered entries are labeled FEE_AND_TREND_FILTER, not fabricated fills.

Exit rules, cooldown, positions/risk limits, delayed frozen FOK execution,
25% visible best-level size cap, account-tier fee assumption and stale-data rules
are unchanged. Open positions retain original exit signals; no forced holding
until break-even, no suppressed stop loss, no maker rebate or cheaper assumed fee.

Deployment: `deploy/start-cbot-fee-filter.sh --apply`. New isolated source bundle
and ledger `/var/lib/cbot/fee-filter-v1.sqlite`, service
`cbot-fee-filter-paper.service`, separate$1,000 virtual wallet, same four products
and existing read-only Coin status feed. No exchange requests/keys added. Reuses
installed dependencies. Original baseline paper service, config and wallet are
NOT restarted/modified. Updates CBot status/UI for comparison and private health
job for optional new service and status checks. Backups automatically include
new*.sqlite ledger. New experiment failures restore original status/UI units,
leave baseline engine running and preserve new ledger for inspection.

Forward comparison at cbot.shaneathon.com uses entries OPENED on/after the new
experiment's persisted start. Earlier baseline P/L and existing positions are
excluded. Baseline retains its earlier cash/daily-loss/drawdown state; bankrolls
are not perfectly matched. Reports trade count, gross, fees, net, notional-
normalized net return and open count; excludes unrealized P/L. Fewer/zero trades
and lower losses do not establish edge. Below30 closed trades in either row is
explicitly INSUFFICIENT_FORWARD_TRADES; beyond that it remains descriptive,
not statistical proof or permission to trade live. No automatic promotion.

Pause new challenger entries via `/var/lib/cbot/STOP-FEE-FILTER` (exits continue).
Original baseline STOP file remains separate. No real-order submission enabled.
