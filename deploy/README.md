# Ten-stream installation preparation

This package is prepared for a separate `btc-multiasset-research.service` on the
existing DigitalOcean droplet. No deployment has been performed. It does not
edit, restart or replace `btc-collector.service` or `btc-challenger.service`.

Streams: BTC/ETH/XRP/SOL × 5m/15m and GOLD/SILVER × 15m. No metals 5m contracts
are invented. Six shared feed requests provide completed 1m candles; each of the
ten streams records its own verified market metadata and observed-time research
prediction. Repeated identical observation timestamps are deduplicated.

## Short console flow (after live prerequisites are validated)

One installation block, executed as root in the droplet console:

```bash
(
  set -euo pipefail
  research_source=$(mktemp -d /tmp/btc-research-source.XXXXXX)
  git -C /root/BTCandThings fetch origin research/ten-stream-setup
  git -C /root/BTCandThings archive FETCH_HEAD | tar -x -C "$research_source"
  bash "$research_source/deploy/install-research.sh" --start
)
```

This fetches the separate preparation branch without checking it out, pulling
into the running checkout, resetting files, or changing production service code.
Git authentication must already work on the droplet; no token is embedded.

The installer builds an isolated release and venv under `/opt`, installs pandas,
runs all 15 collector tests, and then performs a live local-data preflight.
**If any current stream lacks a verified target or fresh sufficient candles,
service activation is refused.** An existing multiasset unit is never overwritten.
It will not secretly deploy only eight markets while claiming all ten work.

After the first collection pass, use one validation command (the installer prints
the exact release-specific command, with no environment activation needed):

```bash
/opt/btcandthings-research/releases/RELEASE/venv/bin/python \
  /opt/btcandthings-research/releases/RELEASE/collection/ten_streams.py \
  --db /var/lib/btcandthings-research/research.sqlite --validate
```

Alternatively, from a copy of this preparation branch:

```bash
bash deploy/validate-research.sh
```

The validation script also prints both existing service states. It never stops
a process. Read-only validation fails if collection status is older than three
minutes, if any stream is missing, if a configured market window has rolled over,
or if any stream was paused. Readiness is per market, not just a running PID.

For install-only staging, `--prepare` runs installation/tests but neither
contacts live markets nor registers/starts services. `BTC_RESEARCH_INSTALL_ROOT`
and `BTC_RESEARCH_STATE_ROOT` may point to temporary directories in this mode.
`--start` requires standard /opt and /var/lib locations and root access.

## What this phase does and does not provide

Local permanent-on-droplet SQLite storage includes candles, checked targets and
contract metadata, raw contract evidence and observed research snapshots. It is
not Supabase synchronization. Prediction timestamps are actual observation times;
source candle timestamps are stored separately. It does not backfill invented
historical predictions. SQLite transactions support restart and retry.

Price sources are Kraken USD spot for crypto, and Yahoo GC=F/SI=F futures proxies
for metals. Metals can be stale during closures or rate-limited. These are not
Chainlink or CF Benchmarks settlement feeds. The installer must wait for fresh
market data or a separately verified alternative source; do not disable the gate.

The report explicitly sets `simulation_ready: false`, `settlement_adapter:
NOT_CONNECTED` and `cloud_storage: NOT_CONNECTED`. Collecting research inputs
is not enough to validate simulated profit/loss. Official outcome-side/finality
mapping, executable quotes, fees, slippage, a reviewed Supabase ingestion adapter,
server disk capacity/retention policy and API request limits still need completion
before the full permanent-history/simulation workflow can be declared ready.
Closed windows are currently revisited one interval back; long-lag settlement
reconciliation requires the future settlement adapter.

Systemd runs as an isolated dynamic user with read-only system paths, private
temporary files and a dedicated state directory. Release files are immutable
while running. Repeated setup creates an independent version rather than editing
code underneath a process. Updates/rollbacks require explicit unit selection and
are deliberately not automatic in the first installer.

## Validation completed here

- 15 collection/audit tests passed, including six feed calls for ten streams,
  metals outage isolation, wrong-asset rejection, duplicate snapshot protection,
  restart validation and stale-status detection.
- The actual `--prepare` installer completed in temporary directories, including
  an isolated venv, dependency installation and its packaged 15-test run.
- Shell syntax checks passed. No systemd installation/start was executed.
- PR #8 was fetched via Git and reviewed. Its separate four-crypto candle script
  is not modified or deployed by this package.
- Live API checks remain blocked by the session's enforced domain allowlist.
  Real Polymarket response compatibility and metal source availability remain
  unverified. Do not call the ten streams live-ready based on fixture tests.

There is no credential configuration step for local shadow collection. Supabase
credentials will be configured securely on the server when its separately tested
integration is ready; never paste secrets into chat or commit an .env file.
