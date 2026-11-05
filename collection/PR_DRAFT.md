# Prepare isolated ten-stream shadow collection and installation

Add a separate collector for BTC/ETH/XRP/SOL 5m+15m and GOLD/SILVER 15m.
Share six feeds across ten market streams, validate asset-specific contracts,
retain candles/contract evidence locally and record research predictions at
observation time. Add an isolated systemd installer that gates activation on
all ten current streams and refuses to overwrite an existing unit. Add read-only
validation with freshness and exact-stream checks.

Preserve existing Champion/Challenger services and all production databases.
Official settlement, Supabase synchronization and simulation accounting remain
unimplemented and explicitly reported as not ready. Real API compatibility is
unverified because the session domain policy denies the required live sources.

Validation: 15 collection/audit tests; real temporary-directory installer prepare
run with isolated dependencies and its packaged tests; shell syntax validation.
PR #8's separate four-crypto collector was reviewed via Git and remains untouched.
No collector service has been deployed; no trades are placed.
