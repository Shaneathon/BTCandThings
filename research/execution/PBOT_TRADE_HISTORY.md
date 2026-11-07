# Last-trade description and complete PBot history

Display-only update requested by user. Current V1 cap remains $10 TOTAL entry
cost including modeled fees per independent wallet, at most one open/pending
position, potentially smaller due to cash/risk/depth/whole-share rounding.
No budget, strategy, fee or execution setting changed.

Each selected wallet's activity now includes the actual latest recorded filled
position, not just its timestamp. Description: market/direction, actual quantity,
weighted average entry, modeled fees, total cost, OPEN/WON/LOST result, payout and
realized net P/L when settled. Requested quantity/order state distinguish partial
fills from planned size. Proposals alone are never described as filled trades.
Payout determines binary winning/losing claim result; net P/L remains its separate
recorded amount after fees. Original fixed-50c experiment ledgers are excluded.

A complete-history checkbox enables a browser for selected wallet or all wallets,
50 rows/page. Private authenticated GET /trades, same loopback server/token as
/status, validates known wallet, page/limit (max100), finite nonfuture anchor,
known ObservedPaperV1 ledger, role/mode/live-disabled and response limit4MB.
No arbitrary path/query SQL interpolation, redirects or token query parameters.
Unsupported Coinbase ledgers return history unavailable. No POST/order endpoints.

SQLite positions are the filled-trade source, joined to corresponding order
plan/state; all records are eligible, not only latest30 displayed by old status.
Sort by filled timestamp descending with stable wallet/market tie-break. Browsing
fixes an as-of timestamp so new trades do not shift page membership; refresh
button resets anchor/page to include latest fills. Settlement fields can update
on refresh; outcomes do not change the filled timestamp. Pages are fetched
separately, never concatenated into the main status/input packet. Latest-trade
summary adds only one compact row per wallet. No ledger/input growth regression.

All displayed trade/settlement timestamps use America/Chicago Central time.
Existing overview, selected metrics, risk/health state and historical reasons
are preserved. Existing refresh-pbot-display.sh deploys ONLY status/UI code and
now verifies the authenticated history endpoint as part of readiness; engines,
exporters, collector services and ledgers remain unchanged. Explicit no-trade
and endpoint-error messages, no invented rows/profits. Tests cover pagination
past30 rows, stable anchors/new fills, auth, bad parameters, read-only behavior,
last-trade details, UI history controls and unchanged10-dollar caption.
