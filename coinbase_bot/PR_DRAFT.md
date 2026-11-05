# Add separate Coinbase spot paper bot and rename Polymarket target to PBot

Change the Polymarket app target/branding/configuration from TBot to
pbot.shaneathon.com. Add the separate cbot.shaneathon.com Coinbase Advanced spot
prototype for BTC/ETH/XRP/SOL USD pairs, with public metadata/candles/book reads,
persistent independent paper holdings/history, cost-aware fills, trend/risk
exits, sizing, cooldown and a separate dashboard/API/deployment templates.

Add shared pre-write ledger guards and explicit status venue validation so the
two apps cannot accidentally use each other's wallet. Both live submission paths
remain unavailable. No tracker main branch, production services, balances, DNS,
certificates or real accounts are changed.

Validation: 16 Polymarket bot tests, 9 Coinbase tests and 6 dashboard fixture
cases passed. Source routes/types checked against Coinbase's official 1.8.4 SDK.
Live Coinbase API requests remain policy-denied; actual compatibility, account
fees and production readiness are not claimed. Strategy parameters are paper
research examples, not a validated edge. Deployment remains a separate step.
