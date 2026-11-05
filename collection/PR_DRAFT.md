# Prepare ten-market collection, cloud history and offline simulation

Add isolated BTC/ETH/XRP/SOL 5m+15m and GOLD/SILVER 15m shadow collection, sharing
six feeds while binding targets and snapshots to each exact market. Retain raw
BBO evidence and reconcile explicit final semantic winners without guessing
numeric side mappings. Add opt-in, retry-safe dedicated-table Supabase sync,
private server-console configuration and read-only per-asset website performance.

Prepare an immutable-release installer with capacity/live-data gates, separate
systemd unit, cloud-aware validation, non-destructive stop command and a durable
connection handoff. Add offline simulated accounting with explicit fees,
slippage and quote timing; unmapped or missing execution data skips trades.

Validation: 24 collector/pipeline tests, 34 website tests, 15 Streamlit fixture
checks and a real isolated --prepare installer rehearsal. Tests use synthetic
HTTP/storage responses; live API semantics, Supabase RLS/constraints and actual
server capacity still need connected verification. Optional scoped-role SQL is
an unexecuted staging draft, not validated production authorization.

Existing Champion/Challenger services, legacy btc_* tables and live trading are
untouched. All new code stays on research/ten-stream-setup; no deployment or
production cloud upload has been performed. PR description prepared locally;
GitHub API access remains blocked, so no PR creation is claimed.
