# Independent four-crypto research collection

Scope: BTC, ETH, XRP, SOL completed one-minute Kraken USD spot proxy candles
and strictly checked Polymarket US 15-minute contract metadata. This is a
separate local-data collector, not a replacement for Pixel Champion or any
existing Challenger service. It has no trading or Supabase write interface.
Python 3.10+ standard library only; no package installation required.

## Local execution

From the repository root, use the existing isolated checkout (no worktree needed):

```sh
python3 -m unittest discover -s collection -v
python3 collection/collector.py --db /tmp/btcandthings-research.sqlite
# Optional continuous local research run; Ctrl+C stops this collector only:
python3 collection/collector.py --db /tmp/btcandthings-research.sqlite --loop
```

The explicit database path is local SQLite. Put retained research data outside
the checkout. WAL mode and per-batch transactions support restarts. Candle keys
match the proposed Supabase table's asset/source/interval/open identity; reruns
update corrections rather than append duplicates. `candles_changed` counts new
or changed local rows, not attempted writes. Reported freshness uses candle close
time. Gaps in each returned batch are counted, not silently filled.

Each pass requests all four assets independently, with 15-second request timeouts
and at most three attempts for transport errors, 429 and selected 5xx responses.
Other HTTP errors are not retried. A one-shot pass exits nonzero on missing/stale
candles or any failed market window. Loop mode reports failures and retries on
the next pass. JSON logs contain error classes, never environment values or
credential-bearing response bodies.

Only bars closed by the fetch-start time are retained. Kraken returns a limited
recent history (typically 720 bars); outages beyond that require a separate
historical backfill source. This implementation does not claim gap-free history.
Kraken prices are proxies, never official CF Benchmarks settlement prices.

## Market verification and limits

The event endpoint and singular full-market endpoint mirror the existing app's
public discovery paths. The direct event must match the requested slug and link
exactly one contract. Full contract identity, typed asset symbol, explicit
UPDOWN/UP_DOWN type, timezone-aware exact window boundaries, and a finite positive
USD target must all agree. Missing or unfamiliar metadata is rejected, never
inferred. Current and previous two windows are revisited each pass. Raw full
contract responses are archived locally with observation times.

**These endpoint/field assumptions have fixture coverage, not live confirmation.**
The app supports broader fallback discovery than this collector; a failed direct
lookup is reported rather than guessed. Supported market-type variants may need
an adapter after inspecting authoritative real responses.

`settlement_status` remains PENDING even when identity and target are verified.
No numeric outcome or proxy price is mapped to UP/DOWN. A separate adapter needs
verified official finality, outcome-side mapping, evidence, and longer pending
window reconciliation before outcomes can become VERIFIED. No predictions are
fabricated for the new assets.

## Validation and remaining deployment work

Locally passed: eleven collection/audit tests (all assets, completed bars, invalid OHLCV,
identity/window/target rejection, duplicate correction handling, database restart,
failure isolation, stale feeds, bounded retries) and 23 existing project tests.

The checkout contains dashboard and historical Champion/Challenger research,
not the production service sources shown in the conversation. Those production
files and unit configurations need read-only comparison before deployment.
Draft PR #8 could not be fetched/reviewed: the configured network proxy is
unreachable; `gh pr view` also reports a proxy socket denial. No remote PR has
been created or updated. See PR_DRAFT.md for the prepared description.

Before requesting deployment approval:

1. Restore authorized network access; inspect PR #8 and reconcile this change.
2. Perform a live read-only smoke run against api.kraken.com and
   gateway.polymarket.us; verify all four exact contract mappings with real data.
3. Review/apply the proposed Supabase migration only with explicit approval.
   Add a separately tested staging ingestion adapter and narrowly scoped backend
   permissions; existing RLS intentionally grants no public access. Local JSON
   records align with candle/window fields, but are not a production uploader.
4. Implement verified settlement reconciliation and validate against known finals.
5. Approve and prepare an independent service with retention, disk monitoring,
   backfill policy, network access and failure alerts; keep existing services.
6. Wire read-only persisted history into the site after ingestion is validated.

Gold/silver, five-minute markets, predictive models, paper trading, and website
changes are outside this collection increment. No production migration,
DigitalOcean deployment, service modification or live trade was performed.

## Read-only audit and export

After collecting local data:

```sh
python3 collection/audit.py --db /tmp/btcandthings-research.sqlite
python3 collection/audit.py --db /tmp/btcandthings-research.sqlite --out /tmp/research-export.json
```

The audit opens SQLite read-only and does not create a missing database. It
reports per-asset candle counts, missing minutes between retained bars,
freshness, and whether current-window contract metadata is verified.
`current_market_verified` refers to identity/terms, never a verified settlement.
The health check requires all four assets, a recent candle, no interior gaps,
current-window metadata and no invalid records. It does not prove upstream data
accuracy or coverage before the first retained candle.

Exports contain `tables.asset_proxy_candles` and `tables.asset_market_windows`
plus the audit summary. They are deterministic for a fixed observation time and
source database. The output file must not already exist. Invalid records block
export; stale or incomplete but valid datasets may be exported with
`healthy: false` and a nonzero exit status. This supports staging review without
network writes. Raw contract evidence is kept in SQLite and excluded from the
export. No uploader, official outcome verification, or database migration is
performed by this command. Supabase compatibility is field-level preparation,
not validation against a running PostgreSQL instance.

## Ten-stream preparation extension

The original `collector.py`/`audit.py` remain the four-crypto 15m workflow.
`ten_streams.py` adds a distinct ten-market local shadow workflow using the
website's asset mappings and research calculations. It requires pandas.
See [the deployment preparation guide](../deploy/README.md) for tested installer
and validation instructions, current limitations and remaining live prerequisites.

Draft PR #8 has now been fetched and reviewed through Git: it adds the separate
`scripts/collect_four_crypto.py` and is not modified here. Git reads work with
supported execution permissions; live APIs still fail the network domain policy.
The older network-block notes above describe the earlier four-crypto increment.
