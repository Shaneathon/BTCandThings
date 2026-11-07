#!/usr/bin/env bash
# Separate PAPER entry-filter experiment. Baseline engine is not restarted.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for file in /var/lib/cbot/fee-filter-v1.sqlite /etc/systemd/system/cbot-fee-filter-paper.service; do
  [[ ! -e "$file" && ! -L "$file" ]] || { echo 'Experiment already exists; preserve it and inspect rather than resetting.'; exit 1; }
done
for name in cbot-paper cbot-status cbot-dashboard; do
  grep -Eq '^WorkingDirectory=/opt/cbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
grep -Fq -- '--observed' /etc/systemd/system/cbot-paper.service
grep -Fq -- '--ledger /var/lib/cbot/observed-v1.sqlite' /etc/systemd/system/cbot-paper.service
[[ -f /etc/cbot-input.env && -f /etc/cbot-paper.json ]]
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/cbot-paper.service)"
task_release="/opt/cbot/releases/filter-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('coinbase_bot','coinbase_tracker','trading_bot','operations'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
ln -s "$task_old/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s coinbase_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
(cd "$task_release"; "$task_release/venv/bin/python" coinbase_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/cbot/filter-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in cbot-status cbot-dashboard shaneathon-health; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_success=0
restore_on_error() {
  if [[ "$task_success" == 0 ]]; then
    systemctl disable --now cbot-fee-filter-paper.service || true
    rm -f /etc/systemd/system/cbot-fee-filter-paper.service
    for name in cbot-status cbot-dashboard shaneathon-health; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    systemctl daemon-reload
    systemctl restart cbot-status cbot-dashboard || true
    echo 'Comparison startup failed; baseline engine was left running. New ledger preserved for inspection.' >&2
  fi
}
trap restore_on_error EXIT
python3 - "$task_release" <<'PY'
from pathlib import Path
import os,sys
release=sys.argv[1]
updates={}
for name in ('cbot-status','cbot-dashboard','shaneathon-health'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    if not old.startswith(('/opt/pbot/releases/','/opt/cbot/releases/','/opt/shaneathon-ops/releases/')): raise SystemExit('Unexpected unit release path')
    updates[path]=text.replace(old,release)
for path,text in updates.items(): path.write_text(text)
unit='''[Unit]
Description=CBot fee-filter paper experiment (no real orders)
After=coin-status.service
[Service]
User=cbot
Group=cbot
WorkingDirectory=RELEASE
EnvironmentFile=/etc/cbot-input.env
ExecStart=RELEASE/venv/bin/python -m coinbase_bot.runner --ledger /var/lib/cbot/fee-filter-v1.sqlite --config /etc/cbot-paper.json --kill-file /var/lib/cbot/STOP-FEE-FILTER --tracker-url http://127.0.0.1:8767/status --loop --observed --fee-filter
Restart=on-failure
RestartSec=15
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/cbot
UMask=0077
CPUQuota=10%
MemoryMax=256M
Nice=10
[Install]
WantedBy=multi-user.target
'''.replace('RELEASE',release)
fd=os.open('/etc/systemd/system/cbot-fee-filter-paper.service',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
with os.fdopen(fd,'w') as f: f.write(unit)
PY
systemctl daemon-reload
systemctl enable --now cbot-fee-filter-paper.service
systemctl restart cbot-status cbot-dashboard
(cd "$task_release"; "$task_release/venv/bin/python" - <<'PY'
import time,json
from coinbase_bot.comparison import compare
for attempt in range(25):
    try:
        report=compare('/var/lib/cbot/observed-v1.sqlite','/var/lib/cbot/fee-filter-v1.sqlite')
        assert report['challenger_status_fresh']
        print(json.dumps(report,indent=2))
        break
    except Exception as error:
        if attempt==24: raise SystemExit('Challenger readiness not established: '+type(error).__name__)
        time.sleep(1)
PY
)
task_success=1
systemctl start --no-block shaneathon-health.service || true
echo 'Separate fee-filter paper experiment running. Original CBot engine, wallet and settings unchanged.'
echo 'Comparison: https://cbot.shaneathon.com . No real trading; fee tier remains estimated.'
echo 'The stricter entry filter may intentionally make few or zero trades. That is not proof of a profitable edge.'
