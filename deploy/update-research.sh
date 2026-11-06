#!/usr/bin/env bash
# Update only the research unit; original collector units are never addressed.
set -euo pipefail
umask 077
mode="${1:---plan}"
if [[ "$mode" != --plan && "$mode" != --apply ]]; then
  echo 'Usage: bash deploy/update-research.sh [--plan|--apply]' >&2; exit 2
fi
if [[ "$EUID" -ne 0 ]]; then echo 'Run on the droplet as root.' >&2; exit 2; fi
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_unit=/etc/systemd/system/btc-multiasset-research.service
task_old_root="$(systemctl show btc-multiasset-research.service --no-pager -p WorkingDirectory --value)"
if [[ "$(systemctl show btc-multiasset-research.service --no-pager -p FragmentPath --value)" != "$task_unit" ]]; then
  echo 'Unexpected unit location; no service changed.' >&2; exit 1
fi
task_log="$(mktemp /tmp/btc-research-update.XXXXXX)"
# Preparation/tests finish while the running service continues using old code.
bash "$task_source_root/deploy/install-research.sh" --prepare | tee "$task_log"
task_new_root="$(python3 - "$task_log" <<'PY'
from pathlib import Path
import re,sys
matches=re.findall(r'^PREPARED: (/opt/btcandthings-research/releases/[A-Za-z0-9_-]+)$',Path(sys.argv[1]).read_text(),re.M)
if len(matches)!=1: raise SystemExit('Could not identify the prepared release')
print(matches[0])
PY
)"
task_rendered="$(mktemp /tmp/btc-research-unit.XXXXXX)"
python3 "$task_new_root/collection/unit_update.py" --unit "$task_unit" --old "$task_old_root" --new "$task_new_root" --out "$task_rendered"
if [[ "$mode" == --plan ]]; then
  echo "Prepared update: $task_old_root -> $task_new_root. No unit or process changed."
  exit 0
fi
mkdir -p /opt/btcandthings-research/unit-backups
task_backup="$(mktemp /opt/btcandthings-research/unit-backups/unit.XXXXXX)"
cp "$task_unit" "$task_backup"
install -m 644 "$task_rendered" "$task_unit"
systemctl daemon-reload
if systemctl restart btc-multiasset-research.service && systemctl is-active --quiet btc-multiasset-research.service; then
  echo 'Research service restarted on tested release; existing collectors were untouched.'
  echo "Validate after its next cycle: $task_new_root/venv/bin/python $task_new_root/collection/ten_streams.py --db /var/lib/btcandthings-research/research.sqlite --validate --require-cloud --record-available"
else
  install -m 644 "$task_backup" "$task_unit"
  systemctl daemon-reload
  systemctl start btc-multiasset-research.service
  echo 'New research release failed immediate startup; original research unit restored.' >&2
  exit 1
fi
