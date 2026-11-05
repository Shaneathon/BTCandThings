# Connect BTCandThings data and TBot paper trading

Resume with:

> I'm ready to connect BTCandThings collection and TBot paper trading. Use
> bot/paper-trading-terminal, deploy/CONNECT_WHEN_READY.md and
> trading_bot/CONNECT_WHEN_READY.md. Keep both existing collectors running,
> preserve btc.shaneathon.com, use tbot.shaneathon.com for the separate bot app,
> and keep real orders disabled.

The bot branch includes the data-preparation branch's code plus the independent
trading_bot/ app. GitHub main still contains the already-published tracker UI;
new bot and cloud-history preparation have not been deployed from this branch.

1. Complete the ten-stream data handoff in deploy/CONNECT_WHEN_READY.md. Verify
   actual sources, targets, final outcomes, protected storage and source identity.
2. Confirm source/API quote-side mapping and actual executable ask size for each
   contract. The raw BBO archive intentionally has unverified semantic mapping;
   do not flip its flag or invent quotes just to get paper positions to open.
3. Create a dedicated bot identity, persistent ledger directory and narrow read
   access to the new collector data or a reviewed read-only snapshot. Leave the
   existing Champion/Challenger files, services and permissions untouched.
4. Install the bot with its example configuration reviewed as paper assumptions.
   Use a separate experiment ledger for future parameter changes. Run one paper
   cycle and inspect readiness/skip reasons before enabling its managed loop.
5. Privately generate the status token and configure the local read-only API and
   separate Streamlit dashboard. Use templates in trading_bot/deploy/, not edits
   to the current BTC website or production virtual host.
6. Create the actual DNS record for tbot.shaneathon.com using the chosen hosting
   endpoint, verify domain routing, then enable TLS and confirm the live site.
   No DNS destination, certificate or new hostname is claimed configured yet.
7. Verify cash, open worst-case risk, ledger persistence across restart, kill
   switch behavior, settlement payouts and non-duplication using real collected
   data. Low history, stale feeds and missing quote mappings must remain visible
   pauses. Default history gate requires 30 settled markets per stream/stage.

This is paper-only commissioning. Live order submission remains unavailable in
code. No paper win rate automatically enables live trading. Real execution is a
separate future implementation/review involving account eligibility, exchange
limits, durable order reconciliation, partial fills, duplicates and explicit
user authorization before real orders.

Completed locally: 16 bot/API/runner tests and 3 Streamlit fixture cases. The
synthetic all-ten-market test is functionality evidence, not an actual trading
record. No secrets have been saved in Git or sent to an exchange.
