# Independent Coinbase paper wallets

User requests actual separate money across BTC/ETH/XRP/SOL, with selecting a
coin changing that coin's P/L. This changes capital allocation, not the entry/
exit hypotheses or fill/fee assumptions. Paper only, no account or real orders.

Prepared migration `deploy/isolate-cbot-wallets.sh --apply` splits each existing
$1,000 starting allocation four ways ($250 per product), for both baseline and
fee-filter experiment. Existing per-product closed-trade P/L is carried forward,
open holdings/costs and exit proposals remain with their product, and cash is
reconstructed as allocation + realized P/L - open cost. The sum must reconcile
with the old shared cash. No money or profit is manufactured or erased.
Unsubmitted BUY proposals cancel without fees when funding budgets change.

Original shared ledgers remain unchanged archive files. New separate ledgers:
`/var/lib/cbot/products/{baseline,fee-filter}/{BTC,ETH,XRP,SOL}-USD.sqlite`.
Each has its own account, config, cash, positions, orders, journal and history.
All-source feeds are scoped to that coin; execution rejects another product.
Funding cannot be drawn from another coin's wallet. Risk/exposure budgets also
split four ways: max daily loss$25 each and exposure$50 each (original totals
$100/$200). The original$50 ticket cap remains an upper limit, but conservative
worst-case-loss budgeting limits new tickets to at most the remaining$25 daily
capacity, plus realized gains. Stops/targets/cooldown remain unchanged. Inherited
larger holdings are managed normally, not force-liquidated to satisfy new caps.
An existing global halt is preserved. New per-product high-water/drawdown uses
its own historical realized path. Negative/unreconcilable allocation aborts.

The two paper engines briefly stop for a consistent read-only migration; source
collectors/PBot keep running. Original units are saved and restored on failure,
old ledgers never edited, and new partial ledgers preserved for inspection.
Refuses existing destination directories/markers. Dependencies reused, actual
isolated source bundle tested. New runner per strategy polls the existing Coin
local API once, then routes data to four independent wallets; no extra exchange
requests. Status aggregation is for transport only, never a spendable treasury.

A global Crypto selector on cbot.shaneathon.com switches baseline cash, reserved/
available cash, cost basis, realized P/L, holdings, trades, journal, config,
chart and per-coin forward comparison together. No conflicting second chart
selector. Coin P/L includes carried history; the forward strategy-comparison
period restarts at isolation to avoid mixing allocation regimes. Old experiment
start is retained. Earlier risk/cash histories still differ across strategies;
comparison remains descriptive and low-sample warnings remain.

Health checks follow new aggregate status files only after readiness marker
PRODUCT-WALLETS-ACTIVE is written. Individual wallet live flags checked. Existing
hourly backup job updated to include eight known nested wallet files as well as
old archives and new aggregate snapshots. All maintenance permissions/schedules
preserved. Read-only review/verification tools detect the new active layout.
CBot fee rates are still estimated at0.6% per side. No real trading enabled.
