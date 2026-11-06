# Consistent backups and unattended health checks

`deploy/install-maintenance.sh --prepare` packages/tests without changing live
services. `--apply` adds three independent root oneshot jobs and timers:

- Hourly consistent SQLite snapshots from known research/paper databases.
- Daily public-data exports of btc_markets, btc_predictions and
  btc_challenger_predictions, using private existing Supabase configuration.
- Health checks every five minutes for services, status freshness, disk/memory,
  recorder gaps, cloud upload errors and explicit live-order flags.

Local state is root-private `/var/lib/shaneathon-ops`. SQLite backup API handles
committed WAL data; each destination is independently integrity-checked before
compression. A backup set becomes complete only after all selected databases
finish. Copies are per-database snapshots, not one cross-database transaction.
Supabase REST exports are paginated with a fixed observation cutoff and are
not an atomic full Supabase/schema/PITR backup. Existing table data is read only.
Credentials are neither printed nor included in these application archives.
Provider full-droplet backups separately include the droplet's protected files.

Only generated completed sets with the tool's manifest marker are rotated:
up to 24 SQLite sets / roughly 4 GiB and 7 cloud-data sets / roughly 1 GiB,
always keeping at least the latest two. The size cap is therefore soft when
two sets alone exceed it. Original databases, raw archives and unknown files
are never deleted. SQLite jobs require an additional 4 GiB disk safety margin
plus twice the current source DB size. Failure leaves the previous completed
sets intact and is logged with no credential values.

The protected portal gets `/health.html`; Nginx's existing password protection
continues to cover it. Local journal/status alerts are implemented; **external
email/SMS/webhook notifications are not configured**. These jobs do not restart
or modify any collector or bot. A critical health report may mark its oneshot
failed so systemd surfaces the problem; this is not an automatic restart request.

DigitalOcean daily backups were enabled by the user. Their first completion
must still be confirmed in the provider dashboard. A local archive is not by
itself off-server protection; the provider backup must capture it successfully.
Backups have not had a complete disaster-recovery rehearsal on another droplet.
Such a rehearsal could incur a separate droplet charge and is not auto-started.

## Restore procedure

1. Restore to a separate directory/machine, never overwrite running ledgers.
2. Verify the selected completed set's manifest and compressed-file hashes.
3. Decompress the desired SQLite file to a new path; run `PRAGMA quick_check`
   and inspect expected tables/counts before connecting an application.
4. Preserve immutable strategy settings and model/experiment IDs. Use a
   separately reviewed service switch if restoring the production app.
5. Restore credentials/TLS separately from the provider's protected backup or
   regenerate them privately; they are deliberately excluded from app archives.
6. Restore Supabase rows only after schema/constraints are in place, with
   explicit review of upserts/conflicts. REST exports are not a schema restore.

After installation inspect `systemctl list-timers 'shaneathon-*'`, the private
portal report and backup manifests. Offsite upload/restore verification and
additional direct alert destinations require separate configuration.
