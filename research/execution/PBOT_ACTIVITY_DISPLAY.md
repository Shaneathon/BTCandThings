# PBot activity and navigation display

User requests retain overview, add easy click-through wallets, show last trades
in Central time and distinguish inactivity from frozen processing. No financial
configuration or execution behavior change is authorized or needed for this UI.

Prepared `deploy/refresh-pbot-display.sh --apply` updates ONLY pbot-status and
pbot-dashboard immutable code paths. Paper engine, exporter, collectors and CBot
are not restarted. Reuses dependencies; actual isolated bundle tested. API
readiness uses the existing private local read token without printing it.
Restores old display/status units on failure. No ledger writes or new services.

The existing complete-market P/L overview stays, with last-trade time and live
state columns added. A horizontal clickable radio selector replaces the less
obvious wallet dropdown; selected wallet shows own cash, realized P/L, cost,
fill count, last filled trade, last settlement processed, last order proposed,
positions and historical reasons. No pooled-wallet or history changes.

Status reader enriches OBSERVED_BOOK_PAPER only through read-only SQLite and
bounded local input reads. All ledger positions/orders are considered for last
activity, not the displayed30 positions. Filled trades come from recorded
positions (including partial fills); proposed/unfilled orders are separate.
Current state derives heartbeat, current input, pause, halt, pending order,
open position/official settlement, remaining risk capacity, current window and
signal/pair freshness. EVALUATING_BOOK_AND_EDGE describes eligibility, not a
claim that every order check passed or a fill is guaranteed. Orders already
attempted this market remain so, not automatically retried by display logic.

Engine/input freshness and all-wallet last fill/settlement indicators appear
above the preserved overview. Healthy waiting, entry window closed, fresh signal
missing, risk exhaustion, awaiting official settlement, stale engine and blocked
input are distinct. Old deduplicated skip timestamps are explicitly labeled
FIRST observations, not current alarms. Books are only requested when eligible;
no-trade time alone is not a freeze detector. API/ledger detail failures surface
as unverified status instead of fabricated activity.

All human timestamps use America/Chicago, including dates, AM/PM and CST/CDT
labels. Numeric UTC epochs in data/ledgers are untouched; display clocks use
actual last-observed times. Standard-time and daylight-saving tests included.
Global overview clocks do not imply every individual wallet traded recently.
Private health/backups/trading decisions and all live submission interlocks
remain unchanged. Real trading stays disabled.
