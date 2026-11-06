#!/usr/bin/env bash
# Install only an observation-mode PBot; never activates paper/live entries.
set -euo pipefail
umask 022
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
task_install_root="${PBOT_INSTALL_ROOT:-/opt/pbot}"
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/pbot ]] || { echo 'Apply requires root and /opt/pbot'; exit 2; }
  for unit in pbot-paper pbot-status pbot-dashboard pbot-input pbot-input.timer; do
    systemctl cat "$unit" >/dev/null 2>&1 && { echo "Existing $unit; refusing replacement"; exit 1; }
  done
  for path in /etc/pbot.env /var/lib/pbot /var/lib/pbot-input; do
    [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing $path; refusing replacement"; exit 1; }
  done
  if getent passwd pbot >/dev/null || getent group pbot >/dev/null; then echo 'Existing pbot identity; refusing replacement'; exit 1; fi
  python3 - <<'PY'
import socket,sqlite3
for port in (8502,8765):
    with socket.socket() as sock: sock.bind(('127.0.0.1',port))
with sqlite3.connect('file:/var/lib/btcandthings-research/research.sqlite?mode=ro',uri=True) as db:
    db.execute('SELECT payload FROM records LIMIT 1').fetchall()
    db.execute('SELECT payload FROM research_snapshots LIMIT 1').fetchall()
print('PBot ports and read-only research source checked.')
PY
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 "$task_source_root/collection/preflight.py" "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for item in (source/'trading_bot').rglob('*.py'):
    if '__pycache__' in item.parts: continue
    dest=target/item.relative_to(source)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(item,dest)
    dest.chmod(0o644)
PY
python3 -m venv "$task_release/venv"
"$task_release/venv/bin/python" -m pip install --disable-pip-version-check -r "$task_source_root/trading_bot/requirements.txt"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -v)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
if [[ "$mode" == --prepare ]]; then echo "PBOT PREPARED: $task_release. No services or users created."; exit 0; fi
useradd --system --user-group --home-dir /var/lib/pbot --no-create-home --shell /usr/sbin/nologin pbot
install -d -m 700 -o pbot -g pbot /var/lib/pbot
install -d -m 750 -o root -g pbot /var/lib/pbot-input
task_pbot_group="$(id -g pbot)"
(cd "$task_release"; "$task_release/venv/bin/python" -m trading_bot.monitor export --source /var/lib/btcandthings-research/research.sqlite --output /var/lib/pbot-input/research.json --group "$task_pbot_group")
python3 - "$task_release" "$task_pbot_group" "$task_source_root" <<'PY'
import os,secrets,sys
from pathlib import Path
release,gid,source=sys.argv[1:]
def exclusive(path,text,mode=0o644):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,'w') as stream: stream.write(text)
exclusive('/etc/pbot.env','PBOT_READ_TOKEN='+secrets.token_hex(32)+'\nPBOT_STATUS_URL=http://127.0.0.1:8765/status\n',0o600)
base='[Unit]\nDescription=PBot research observation (entries disabled)\nAfter=network-online.target\n[Service]\n'
guard='\nNoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=yes\nUMask=0077\n'
watch=(base+'User=pbot\nGroup=pbot\nWorkingDirectory='+release+'\nExecStart='+release+'/venv/bin/python -m trading_bot.monitor watch --input /var/lib/pbot-input/research.json --ledger /var/lib/pbot/paper.sqlite --loop\nRestart=on-failure\nRestartSec=15\nReadWritePaths=/var/lib/pbot'+guard+'[Install]\nWantedBy=multi-user.target\n')
exclusive('/etc/systemd/system/pbot-paper.service',watch)
export=(base+'Type=oneshot\nUser=root\nWorkingDirectory='+release+'\nExecStart='+release+'/venv/bin/python -m trading_bot.monitor export --source /var/lib/btcandthings-research/research.sqlite --output /var/lib/pbot-input/research.json --group '+gid+'\nReadWritePaths=/var/lib/pbot-input'+guard)
exclusive('/etc/systemd/system/pbot-input.service',export)
exclusive('/etc/systemd/system/pbot-input.timer','[Unit]\nDescription=Refresh read-only PBot research snapshot\n[Timer]\nOnBootSec=30\nOnUnitActiveSec=60\nUnit=pbot-input.service\n[Install]\nWantedBy=timers.target\n')
for name in ('pbot-status','pbot-dashboard'):
    text=(Path(source)/'trading_bot'/'deploy'/(name+'.service')).read_text()
    text=text.replace('/opt/pbot',release).replace('ProtectHome=yes\n','ProtectHome=yes\nReadWritePaths=/var/lib/pbot\n')
    exclusive('/etc/systemd/system/'+name+'.service',text)
print('Private read token generated; value not displayed.')
PY
systemctl daemon-reload
systemctl enable --now pbot-input.timer pbot-paper.service pbot-status.service pbot-dashboard.service
echo "PBOT INSTALLED: $task_release"
echo 'Observation only. Paper entries hard-disabled. Live orders disabled. Existing collectors unchanged.'
echo 'Dashboard: loopback 8502. Private API: loopback 8765. DNS/HTTPS remain separate.'
