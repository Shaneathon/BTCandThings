#!/usr/bin/env bash
# New read-only health/backup jobs only; never restart application services.
set -euo pipefail
umask 077
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_install_root="${OPS_INSTALL_ROOT:-/opt/shaneathon-ops}"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/shaneathon-ops ]] || { echo 'Apply requires root and standard paths'; exit 2; }
  for name in shaneathon-backup shaneathon-cloud-export shaneathon-health; do
    for suffix in service timer; do
      if systemctl cat "$name.$suffix" >/dev/null 2>&1; then echo "Existing $name.$suffix; refusing replacement"; exit 1; fi
    done
  done
  [[ ! -e /var/lib/shaneathon-ops && ! -L /var/lib/shaneathon-ops ]] || { echo 'Existing operations state; inspect before installing'; exit 1; }
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release/operations"
# Parent code paths must be searchable by root; source contains no secrets.
chmod 755 "$task_install_root" "$task_install_root/releases" "$task_release" "$task_release/operations"
cp "$task_source_root"/operations/*.py "$task_release/operations/"
chmod 644 "$task_release"/operations/*.py
(cd "$task_release"; python3 -m unittest operations.test_maintenance -v)
if [[ "$mode" == --prepare ]]; then echo "MAINTENANCE PREPARED: $task_release. No units or production state changed."; exit 0; fi
install -d -m 700 -o root -g root /var/lib/shaneathon-ops
python3 - "$task_release" <<'PY'
import os,sys
release=sys.argv[1]
jobs=[('shaneathon-backup','backup','hourly'),
      ('shaneathon-cloud-export','cloud','*-*-* 03:10:00 UTC'),
      ('shaneathon-health','health','*:0/5')]
for name,job,schedule in jobs:
    env='EnvironmentFile=-/root/BTCandThings/collector/.env\n' if job=='cloud' else ''
    writable='/var/lib/shaneathon-ops'
    if job=='health': writable+=' -/var/www/shaneathon-portal'
    text=('[Unit]\nDescription=Shaneathon '+job+' maintenance (no trading or service changes)\n'
          '[Service]\nType=oneshot\nUser=root\nWorkingDirectory='+release+'\n'+env+
          'ExecStart=/usr/bin/python3 -m operations.maintenance '+job+'\n'
          'NoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=read-only\n'
          'ReadWritePaths='+writable+'\nUMask=0077\nNice=10\nCPUQuota=20%\nMemoryMax=256M\nTimeoutStartSec=15min\n')
    timer=('[Unit]\nDescription=Scheduled Shaneathon '+job+'\n[Timer]\nOnCalendar='+schedule+
           '\nPersistent=true\nRandomizedDelaySec=30\nUnit='+name+'.service\n[Install]\nWantedBy=timers.target\n')
    for suffix,body in [('service',text),('timer',timer)]:
        fd=os.open('/etc/systemd/system/'+name+'.'+suffix,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
        with os.fdopen(fd,'w') as output: output.write(body)
PY
systemctl daemon-reload
echo 'Creating the first consistent local backup; applications keep running.'
if ! systemctl start shaneathon-backup.service; then
  echo 'The first backup failed; scheduled retries remain available. Recent backup log:'
  journalctl -u shaneathon-backup.service -n 20 --no-pager
fi
systemctl enable --now shaneathon-backup.timer shaneathon-cloud-export.timer shaneathon-health.timer
systemctl start --no-block shaneathon-cloud-export.service
# A critical health report is itself useful; do not stop or restart apps to hide it.
if ! systemctl start shaneathon-health.service; then echo 'Health check detected an issue; see the report below.'; fi
python3 - <<'PY'
from pathlib import Path
import json
root=Path('/var/lib/shaneathon-ops')
for name in ('backup-status.json','backup-failure.json','cloud-status.json','health.json'):
    path=root/name
    print('\n'+name)
    if path.exists(): print(path.read_text())
    elif name=='backup-failure.json': print('No backup failure recorded.')
    else: print('No completed status yet; scheduled jobs remain enabled. Cloud export may still be running.')
PY
echo 'MAINTENANCE INSTALLED: hourly SQLite snapshots, daily public cloud-data exports, health checks every five minutes.'
echo 'Private report: https://shaneathon.com/health.html (portal login required).'
echo 'No collectors/bots were restarted, and no paid service was enabled.'
