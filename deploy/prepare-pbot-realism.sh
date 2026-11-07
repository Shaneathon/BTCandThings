#!/usr/bin/env bash
# First migration step: stop new artificial-price entries; gather real book evidence.
set -euo pipefail
umask 077
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /var/lib/pbot/comparison.sqlite && -f /var/lib/btcandthings-research/research.sqlite ]]
grep -Fq ' -m trading_bot.dual_sandbox watch ' /etc/systemd/system/pbot-paper.service || { echo 'Unexpected PBot engine; no changes made'; exit 1; }
# Existing engine checks this file each cycle. Do not stop settlement accounting.
[[ ! -L /var/lib/pbot/STOP-SANDBOX ]] || { echo 'Unexpected pause-file symlink'; exit 1; }
touch /var/lib/pbot/STOP-SANDBOX
chown root:pbot /var/lib/pbot/STOP-SANDBOX
chmod 640 /var/lib/pbot/STOP-SANDBOX
echo 'New fixed-50c entries paused. Existing ledgers, settlement processing and collectors are preserved.'
cd "$task_source_root"
/root/BTCandThings/venv/bin/python -m unittest trading_bot.tests.test_execution_audit -q
/root/BTCandThings/venv/bin/python -m trading_bot.execution_audit \
  --source /var/lib/btcandthings-research/research.sqlite \
  --output /var/lib/pbot-execution-audit
echo 'This prepares the migration; it does not activate the replacement paper execution engine.'
echo 'Real orders remain disabled. Send back the audit output to finish the provider-specific adapter.'
