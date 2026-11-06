#!/usr/bin/env bash
# Update only PBot to a clearly hypothetical, forward directional experiment.
set -euo pipefail
umask 022
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
task_install_root="${PBOT_INSTALL_ROOT:-/opt/pbot}"
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/pbot ]] || { echo 'Apply requires root and standard paths'; exit 2; }
  id pbot >/dev/null
  [[ -f /etc/pbot.env && -f /root/BTCandThings/collector/.env ]] || { echo 'Missing private configuration'; exit 1; }
  grep -Fq ' -m trading_bot.monitor watch ' /etc/systemd/system/pbot-paper.service || { echo 'Expected observation-mode PBot; refusing unknown unit'; exit 1; }
  grep -Fq -- '--ledger /var/lib/pbot/paper.sqlite' /etc/systemd/system/pbot-status.service || { echo 'Unexpected PBot status ledger'; exit 1; }
  for name in pbot-paper pbot-status pbot-dashboard; do
    grep -Eq '^WorkingDirectory=/opt/pbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo "Unexpected $name path"; exit 1; }
  done
  for path in /var/lib/pbot/comparison.sqlite /var/lib/pbot/champion-directional-v1.sqlite /var/lib/pbot/challenger-b-directional-v1.sqlite /etc/systemd/system/pbot-sandbox-input.service /etc/systemd/system/pbot-sandbox-input.timer; do
    [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing $path; preserve experiment and review before retry"; exit 1; }
  done
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
    shutil.copyfile(item,dest);dest.chmod(0o644)
PY
python3 -m venv "$task_release/venv"
"$task_release/venv/bin/python" -m pip install --disable-pip-version-check -r "$task_source_root/trading_bot/requirements.txt"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -v)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
if [[ "$mode" == --prepare ]]; then echo "SANDBOX PREPARED: $task_release. No running services changed."; exit 0; fi
task_pbot_group="$(id -g pbot)"
(
  set +x
  set -a
  source /root/BTCandThings/collector/.env
  set +a
  cd "$task_release"
  "$task_release/venv/bin/python" -m trading_bot.dual_sandbox export --source /var/lib/btcandthings-research/research.sqlite --input /var/lib/pbot-input/dual-sandbox.json --group "$task_pbot_group"
)
task_backup="$(mktemp -d /opt/pbot/unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
python3 - "$task_release" "$task_pbot_group" <<'PY'
from pathlib import Path
import os,sys
release,gid=sys.argv[1:]
base='[Unit]\nDescription=PBot hypothetical directional experiment (no real orders)\nAfter=network-online.target\n[Service]\n'
guard='\nNoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=yes\nUMask=0077\n'
watch=(base+'User=pbot\nGroup=pbot\nWorkingDirectory='+release+'\nExecStart='+release+'/venv/bin/python -m trading_bot.dual_sandbox watch --input /var/lib/pbot-input/dual-sandbox.json --state /var/lib/pbot\nRestart=on-failure\nRestartSec=15\nReadWritePaths=/var/lib/pbot'+guard+'[Install]\nWantedBy=multi-user.target\n')
Path('/etc/systemd/system/pbot-paper.service').write_text(watch)
for name in ('pbot-status','pbot-dashboard'):
    path=Path('/etc/systemd/system')/(name+'.service')
    text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    text=text.replace(old,release)
    if name=='pbot-status': text=text.replace('--ledger /var/lib/pbot/paper.sqlite','--ledger /var/lib/pbot/comparison.sqlite')
    path.write_text(text)
export=(base+'Type=oneshot\nUser=root\nWorkingDirectory='+release+'\nEnvironmentFile=/root/BTCandThings/collector/.env\nExecStart='+release+'/venv/bin/python -m trading_bot.dual_sandbox export --source /var/lib/btcandthings-research/research.sqlite --input /var/lib/pbot-input/dual-sandbox.json --group '+gid+'\nReadWritePaths=/var/lib/pbot-input'+guard)
timer='[Unit]\nDescription=Fetch public Champion and Challenger predictions for sandbox\n[Timer]\nOnBootSec=10\nOnUnitActiveSec=10\nUnit=pbot-sandbox-input.service\n[Install]\nWantedBy=timers.target\n'
for name,text in [('pbot-sandbox-input.service',export),('pbot-sandbox-input.timer',timer)]:
    fd=os.open('/etc/systemd/system/'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    with os.fdopen(fd,'w') as stream: stream.write(text)
PY
systemctl daemon-reload
systemctl enable --now pbot-sandbox-input.timer
task_start_ok=1
if ! systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service; then task_start_ok=0; fi
for name in pbot-paper pbot-status pbot-dashboard; do
  if ! systemctl is-active --quiet "$name.service"; then task_start_ok=0; fi
done
if [[ "$task_start_ok" == 0 ]]; then
  for name in pbot-paper pbot-status pbot-dashboard; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
  systemctl disable --now pbot-sandbox-input.timer
  systemctl daemon-reload
  systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service
  echo 'PBot immediate startup failed; observation services restored. New experiment files preserved.' >&2
  exit 1
fi
echo "PBOT DIRECTIONAL SANDBOX INSTALLED: $task_release"
echo 'Two independent $1,000 virtual wallets. Hypothetical 50c reference price, 1c fee and 1c slippage per share.'
echo 'Only forward BTC 15m signals, final 90–30 seconds. Actual market fills and all live orders remain disabled.'
echo 'Existing collectors and Coinbase unchanged. PBot dashboard: https://pbot.shaneathon.com'
python3 - <<'PY'
import json,sqlite3,time
for attempt in range(20):
    try:
        with sqlite3.connect('file:/var/lib/pbot/comparison.sqlite?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()
        report=json.loads(row[0])
        if not 0<=time.time()-report['observed_at']<=30: raise ValueError('Awaiting fresh status')
        assert report['account']['live_orders_enabled'] is False
        assert report['executable_quote_fills_enabled'] is False
        print('Input:',report['input_status'],'| Shared signal markets:',report['common_signal_markets'])
        for name,state in report['portfolios'].items():
            account=state['account']
            print(name,'| virtual cash:',account['cash'],'| hypothetical P/L:',account['realized_pnl'],
                  '| recorded entries:',account['position_count'],'| live orders:',account['live_orders_enabled'])
        break
    except (sqlite3.Error,TypeError,KeyError,ValueError):
        if attempt==19:
            print('Sandbox status is not ready yet; inspect pbot-paper logs before assuming entry readiness.')
        else: time.sleep(1)
PY
