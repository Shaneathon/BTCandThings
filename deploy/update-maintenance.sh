#!/usr/bin/env bash
# Update only short-lived maintenance code; preserve timers, backups and apps.
set -euo pipefail
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---plan}"
[[ "$mode" == --plan || "$mode" == --apply ]] || { echo 'Use --plan or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 ]] || { echo 'Apply requires root'; exit 2; }
  for name in shaneathon-backup shaneathon-cloud-export shaneathon-health; do
    grep -Eq '^WorkingDirectory=/opt/shaneathon-ops/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo 'Unexpected maintenance unit'; exit 1; }
  done
fi
task_log="$(mktemp)"
bash "$task_source_root/deploy/install-maintenance.sh" --prepare | tee "$task_log"
task_release="$(sed -n 's/^MAINTENANCE PREPARED: \(.*\)\. No units or production state changed\.$/\1/p' "$task_log")"
[[ -f "$task_release/operations/maintenance.py" ]] || { echo 'Prepared maintenance release missing'; exit 1; }
if [[ "$mode" == --plan ]]; then echo 'Maintenance update prepared; no units changed.'; exit 0; fi
[[ "$task_release" == /opt/shaneathon-ops/releases/* ]] || { echo 'Expected standard maintenance path'; exit 1; }
task_backup="$(mktemp -d /opt/shaneathon-ops/unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in shaneathon-backup shaneathon-cloud-export shaneathon-health; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
for name in ('shaneathon-backup','shaneathon-cloud-export','shaneathon-health'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    path.write_text(text.replace(old,sys.argv[1]))
PY
systemctl daemon-reload
if ! systemctl start shaneathon-health.service; then echo 'Health report has alerts; inspect the protected report.'; fi
echo 'Maintenance reader updated. Timers, backups and all application services preserved.'
