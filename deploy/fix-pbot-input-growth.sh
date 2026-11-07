#!/usr/bin/env bash
# Compact the live packet, preserve source history and existing paper ledger.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /var/lib/pbot/OBSERVED-ACTIVE && -f /var/lib/pbot/observed-v1.sqlite ]]
grep -Fq ' -m trading_bot.observed_paper ' /etc/systemd/system/pbot-paper.service
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input shaneathon-health; do
  grep -Eq '^WorkingDirectory=/opt/pbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo "Unexpected $name unit; no changes made"; exit 1; }
done
task_old_release="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
task_release="/opt/pbot/releases/input-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('trading_bot','coinbase_bot','operations'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
ln -s "$task_old_release/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/pbot/input-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input shaneathon-health; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_committed=0
restore_on_failure() {
  if [[ "$task_committed" == 0 ]]; then
    for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input shaneathon-health; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    systemctl daemon-reload
    systemctl restart pbot-paper pbot-status pbot-dashboard || true
    systemctl start pbot-sandbox-input.timer || true
    echo 'Prior service units restored after failure. Ledger and collector history preserved.' >&2
  fi
}
trap restore_on_failure EXIT
# Only the bot input exporter is paused, not any underlying collector. Avoid an
# old in-flight export overwriting the newly bounded file during transition.
systemctl stop pbot-sandbox-input.timer pbot-sandbox-input.service
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
updates={}
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-sandbox-input','shaneathon-health'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    updates[path]=text.replace(old,sys.argv[1])
for path,text in updates.items(): path.write_text(text)
PY
systemctl daemon-reload
systemctl start pbot-sandbox-input.service
python3 - <<'PY'
from pathlib import Path
import json
p=Path('/var/lib/pbot-input/dual-sandbox.json')
size=p.stat().st_size
assert size<=8_000_000,'New export still exceeds engine byte limit'
data=json.loads(p.read_text())
print('Bounded input:',size,'bytes | markets:',len(data['markets']),'| predictions:',len(data['predictions']))
PY
systemctl restart pbot-paper pbot-status pbot-dashboard
systemctl start pbot-sandbox-input.timer
python3 - <<'PY'
import sqlite3,json,time
for attempt in range(25):
    try:
        with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
            row=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        data=json.loads(row[1])
        assert 0<=time.time()-row[0]<10 and data['input_status']=='FRESH' and not data.get('input_error')
        assert data['account']['live_orders_enabled'] is False
        print('PBot input FRESH; live orders disabled; existing paper balances preserved.')
        break
    except (sqlite3.Error,TypeError,KeyError,AssertionError):
        if attempt==24: raise SystemExit('Fresh bounded input readiness not established')
        time.sleep(1)
PY
task_committed=1
systemctl start --no-block shaneathon-health.service || true
echo 'Live packet growth fixed. Full history remains in collector/ledger databases.'
echo 'Coinbase and underlying collectors were not restarted. No real trading.'
(cd "$task_release"; "$task_release/venv/bin/python" -m trading_bot.activity --hours 6)
