#!/usr/bin/env bash
# Frontend-only release. No engine, API, input, or financial changes.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_backup="$(mktemp -d /tmp/bot-display-units.XXXXXX)"
chmod 700 "$task_backup"
for bot in pbot cbot; do
  task_unit="/etc/systemd/system/$bot-dashboard.service"
  grep -Eq "^WorkingDirectory=/opt/$bot/releases/[A-Za-z0-9_-]+$" "$task_unit"
  cp "$task_unit" "$task_backup/$bot-dashboard.service"
  task_old="$(sed -n 's/^WorkingDirectory=//p' "$task_unit")"
  task_release="/opt/$bot/releases/compact-$(date -u +%Y%m%dT%H%M%S)-$$"
  mkdir -p "$task_release"
  python3 - "$task_source" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('trading_bot','coinbase_bot','coinbase_tracker'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
  ln -s "$task_old/venv" "$task_release/venv"
  task_package=trading_bot
  [[ "$bot" == cbot ]] && task_package=coinbase_bot
  (cd "$task_release"; "$task_release/venv/bin/python" "$task_package/smoke_ui.py")
  printf '%s\n' "$task_release" > "$task_backup/$bot-release"
done
task_done=0
restore_on_failure() {
  if [[ "$task_done" == 0 ]]; then
    for bot in pbot cbot; do cp "$task_backup/$bot-dashboard.service" "/etc/systemd/system/$bot-dashboard.service"; done
    systemctl daemon-reload
    systemctl restart pbot-dashboard cbot-dashboard || true
    echo 'Prior dashboard units restored; engines and ledgers unchanged.' >&2
  fi
}
trap restore_on_failure EXIT
for bot in pbot cbot; do
  python3 - "$bot" "$(cat "$task_backup/$bot-release")" <<'PY'
from pathlib import Path
import sys
path=Path('/etc/systemd/system')/(sys.argv[1]+'-dashboard.service')
text=path.read_text();old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
path.write_text(text.replace(old,sys.argv[2]))
PY
done
systemctl daemon-reload
systemctl restart pbot-dashboard cbot-dashboard
python3 - <<'PY'
import time
from urllib.request import urlopen
for port in (8502,8503):
    for attempt in range(30):
        try:
            with urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=2) as response:
                assert response.read(100)==b'ok'
            break
        except Exception:
            if attempt==29: raise
            time.sleep(1)
PY
systemctl is-active --quiet pbot-dashboard cbot-dashboard
task_done=1
echo 'Compact PBot and CBot dashboards installed. Refresh both pages.'
echo 'Only dashboard services restarted. Engines, collectors, wallets, entry limits and live-order settings unchanged.'
