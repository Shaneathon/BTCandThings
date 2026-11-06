# Prepared ten-stream installation

The full handoff is [CONNECT_WHEN_READY.md](CONNECT_WHEN_READY.md). This package
has been tested locally but not deployed to DigitalOcean or production Supabase.
Existing btc-collector.service and btc-challenger.service are never edited or
restarted. The independent new unit is btc-multiasset-research.service.

## Short setup flow — use after the connected preflight

After confirming real API responses, additive schema and staging permissions,
run one block as root in the droplet console:

```bash
(
  set -euo pipefail
  research_source=$(mktemp -d /tmp/btc-research-source.XXXXXX)
  git -C /root/BTCandThings fetch origin research/ten-stream-setup
  git -C /root/BTCandThings archive FETCH_HEAD | tar -x -C "$research_source"
  bash "$research_source/deploy/install-research.sh" --start-cloud
)
```

This does not pull/reset/switch the running checkout. It prepares an immutable
release, an isolated venv, capacity checks, all packaged collector tests and a
live ten-stream preflight. Only after preflight passes does it privately ask for
the Supabase URL and hidden server key, verify research-table read access, save
root-mode-600 configuration and start the separate service. It refuses to
overwrite an existing unit or credential file. No credentials belong in chat.

The installer prints one exact release-specific validation command. Cloud-enabled
installation uses `--validate --require-cloud`: stale status, expired windows,
missing streams, sync errors or a possible upload backlog produce a nonzero exit.
Repeated runs drain the bounded upload backlog. Individual quote and settlement
readiness are reported separately; collection success is not simulation readiness.

From a copy of this branch, an equivalent command also prints existing service
states without changing them:

```bash
bash deploy/validate-research.sh --require-cloud
```

Use `--start` for local shadow storage only, or `--prepare` for package installation
and tests without live requests or systemd changes. Preparation supports
BTC_RESEARCH_INSTALL_ROOT and BTC_RESEARCH_STATE_ROOT overrides for temporary
rehearsals. Activation uses the standard /opt and /var/lib paths only.

## Components

- Six price feeds shared across ten market streams, exact typed contract checks,
  completed candles and actual observation-time research snapshots in SQLite.
- Raw Polymarket BBO evidence (SDK-confirmed route), with side mapping explicitly
  pending. It is not silently treated as executable UP/DOWN fills.
- Explicit semantic winner settlement reconciliation with pending-queue rotation,
  retained evidence and no downgrade of final local outcomes.
- Opt-in cloud sync to only three dedicated asset_* tables. Natural keys and
  checkpoints support restarts/retries; target, identity and final-winner
  conflicts are never silently overwritten.
- Read-only per-asset website performance wiring, prepared on this branch.
- Offline simulation calculator requiring reviewed normalized quotes and explicit
  fees/slippage. It places no orders and is not a portfolio/liquidity simulator.

Raw quote evidence is not uploaded as mapped quotes. Paper trade reports stay
local; there is no automatic paper-trade cloud uploader. The original
collector.py/audit.py retain the separate four-crypto workflow; ten_streams.py
and its --validate mode handle this ten-stream workflow.

## Capacity and remaining live requirements

Installer gate: 1 GiB free disk and 256 MiB available RAM. Runtime pauses new
collection below 100 MiB free disk. No automatic historical deletion occurs;
plan retention, cloud backups and monitoring before extended unattended runs.

Kraken spot and Yahoo GC=F/SI=F futures are proxy feeds, not official settlement
sources. Yahoo closures/rate limits and real Polymarket response compatibility
still require live verification. Missing or stale metals data fails the
all-ten activation gate; do not disable that gate to claim full readiness.

Supabase SQL remains unapplied. Review proposed_multi_asset_schema.sql and the
optional scoped-role draft in staging. The current key-based transport does not
refresh scoped-user JWTs. Server keys can bypass RLS and must remain private.
No extra credentials are needed for public local shadow collection.

## Validation

24 collector/pipeline tests, 34 website unit tests and 15 Streamlit fixture checks
pass. A real temporary-directory --prepare run installed dependencies and ran
its packaged collector tests. Shell syntax passed. HTTP cloud fixtures cover
end-to-end collection, settlement, retries and simulation but do not validate
actual PostgreSQL constraints/RLS or production credentials.

No systemd start, production migration, real Supabase upload, DigitalOcean
connection or live trade was performed. New website history wiring remains on
this preparation branch, so the already-live site is unchanged.

## Explicit available-data recording mode

Live preflight confirmed valid metadata for all ten streams and working crypto
prices, but Yahoo returned 429 for both metals and a current BTC 5m BBO returned
404. These are reported missing observations, not permission to substitute feeds.

`--start-recording` and `--start-cloud-recording` now select the explicit
`--record-available` mode. Activation still requires all ten exact current market
identities/targets, but does not pretend every price/book is available. Full
`collection_ready` stays false where necessary; `recording_ready` is a separate
metadata-coverage and freshness measure. Strict original modes remain available.
No trade execution is enabled. Validation can use --record-available alongside
--require-cloud and reports the complete coverage gaps.

HTTP 429 is no longer retried immediately. Price-feed cooldowns persist in SQLite,
honor numeric/HTTP-date Retry-After, and default to 15 minutes when absent.
Existing saved 429 evidence seeds the initial cooldown on upgrade. Do not run
repeated manual probes against the rate-limited source or rotate hosts/IPs.

For an authorized server setup, BTC_RESEARCH_REUSE_COLLECTOR_ENV=1 lets the private
wizard reuse SUPABASE_URL/KEY already loaded into its process from the existing
collector configuration. It never displays either value and still exclusively
creates its separate root-mode-600 environment file. Role/read/write access must
be verified; a readable legacy table alone does not establish research-table
write permission. The existing collector's config is not edited.

Cloud candle/prediction uploads are grouped into batches of up to 100 rows.
A failed batch receives no checkpoints and retries by natural keys. Metadata
identity/finality checks remain per market. Optional BTC_RESEARCH_SEED_DB seeds a
new preflight database using SQLite's consistent backup API. A successful
preflight is then copied into an absent research.sqlite before activation,
preserving real observations and rate-limit cooldowns. No existing database is
overwritten. This path and batched failure/recovery bring the local suite to
31 passing tests; a complete temporary --prepare rehearsal also passed.

### Immutable research-service updates

The live collector confirmed successful cloud batches, with quote 429 responses
remaining. Quotes are now queued after prediction capture, spaced at least 1.5
seconds apart in real-clock mode, and globally cooled down on 429 according to
Retry-After (60 seconds if absent). Least-recently-attempted streams are rotated
first so paused requests do not permanently favor the first few markets. A 404
is still unavailable data, not a substituted contract. No extra manual BBO probes
are needed during cooldown.

`bash deploy/update-research.sh --apply` prepares/tests a new immutable release
while the old service runs, preserves the current unit privately, switches only
its release paths and restarts only btc-multiasset-research.service. The database,
cloud checkpoints, environment file and recording-mode flag remain unchanged.
Immediate restart failure restores the prior research unit. `--plan` prepares and
renders the change without modifying a unit or restarting a process. Deferred
functional failure still needs the printed validation/log check; a PID alone
is not full readiness. The original Champion/Challenger units are never addressed.
36 local collector tests now pass, including pacing, cooldown and unit rendering.
