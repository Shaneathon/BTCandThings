#!/usr/bin/env bash
# Independent Coinbase paper wallet using the existing read-only Coin feed.
set -euo pipefail
umask 022
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_install_root="${CBOT_INSTALL_ROOT:-/opt/cbot}"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/cbot ]] || { echo 'Apply requires root and /opt/cbot'; exit 2; }
  for name in cbot-paper cbot-status cbot-dashboard; do
    if systemctl cat "$name.service" >/dev/null 2>&1; then echo "Existing $name; refusing replacement"; exit 1; fi
  done
  for path in /etc/cbot.env /etc/cbot-input.env /etc/cbot-paper.json /var/lib/cbot; do
    [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing $path; refusing replacement"; exit 1; }
  done
  if getent passwd cbot >/dev/null || getent group cbot >/dev/null; then echo 'Existing cbot identity; refusing replacement'; exit 1; fi
  [[ -f /etc/coin.env ]] || { echo 'Coin tracker private read token configuration missing'; exit 1; }
  for name in coin-collector coin-status; do systemctl is-active --quiet "$name.service"; done
  python3 - <<'PY'
import socket
for port in (8503,8766):
    with socket.socket() as sock: sock.bind(('127.0.0.1',port))
print('CBot ports available; existing Coin services active.')
PY
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 "$task_source_root/collection/preflight.py" "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('coinbase_bot','coinbase_tracker','trading_bot'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
shutil.copyfile(source/'coinbase_bot/paper.example.json',target/'paper.json')
PY
python3 -m venv "$task_release/venv"
"$task_release/venv/bin/python" -m pip install --disable-pip-version-check -r "$task_source_root/coinbase_bot/requirements.txt"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s coinbase_bot/tests -v)
(cd "$task_release"; "$task_release/venv/bin/python" coinbase_bot/smoke_ui.py)
if [[ "$mode" == --prepare ]]; then echo "CBOT PREPARED: $task_release. No services or users created."; exit 0; fi
# Preflight performs authenticated GET to the local research API, not Coinbase trading endpoints.
(cd "$task_release"; "$task_release/venv/bin/python" - <<'PY'
from pathlib import Path
import re
from coinbase_tracker.client import fetch,bot_inputs
values=[line.split('=',1)[1].strip() for line in Path('/etc/coin.env').read_text().splitlines() if line.startswith('COIN_READ_TOKEN=')]
if len(values)!=1 or not re.fullmatch('[0-9a-f]{64}',values[0]): raise ValueError('Expected generated private Coin read token')
report=fetch('http://127.0.0.1:8767/status',values[0])
inputs=bot_inputs(report)
for product,source in inputs.items(): print(product,'input:',source.get('error','READY'))
if not inputs or any(source.get('error') for source in inputs.values()): raise ValueError('Wait for all four fresh Coin inputs before installing CBot')
PY
)
useradd --system --user-group --home-dir /var/lib/cbot --no-create-home --shell /usr/sbin/nologin cbot
install -d -m 700 -o cbot -g cbot /var/lib/cbot
python3 - "$task_source_root" "$task_release" <<'PY'
import os,secrets,sys
from pathlib import Path
source,release=sys.argv[1:]
def exclusive(path,text,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,'w') as stream: stream.write(text)
token=next(line for line in Path('/etc/coin.env').read_text().splitlines() if line.startswith('COIN_READ_TOKEN='))
exclusive('/etc/cbot-input.env',token+'\n',0o600)
exclusive('/etc/cbot.env','CBOT_READ_TOKEN='+secrets.token_hex(32)+'\nCBOT_STATUS_URL=http://127.0.0.1:8766/status\n',0o600)
exclusive('/etc/cbot-paper.json',(Path(release)/'paper.json').read_text(),0o644)
for name in ('cbot-paper','cbot-status','cbot-dashboard'):
    text=(Path(source)/'coinbase_bot/deploy'/(name+'.service')).read_text().replace('/opt/cbot',release)
    if name=='cbot-paper':
        text=text.replace('WorkingDirectory='+release+'\n','WorkingDirectory='+release+'\nEnvironmentFile=/etc/cbot-input.env\n')
        text=text.replace('--loop','--tracker-url http://127.0.0.1:8767/status --loop')
    else:
        text=text.replace('ProtectHome=yes\n','ProtectHome=yes\nReadWritePaths=/var/lib/cbot\n')
    exclusive('/etc/systemd/system/'+name+'.service',text,0o644)
print('CBot read credentials configured privately; values not displayed. No Coinbase trading keys used.')
PY
systemctl daemon-reload
systemctl enable --now cbot-paper.service cbot-status.service cbot-dashboard.service
echo "CBOT INSTALLED: $task_release"
echo 'Paper only. Separate $1,000 virtual wallet; sampled Coinbase quotes with assumed fees/slippage.'
echo 'BTC-USD, ETH-USD, XRP-USD, SOL-USD; no live orders, no leverage, no shorting.'
echo 'Existing collectors and PBot unchanged. Dashboard loopback 8503; API loopback 8766.'
python3 - <<'PY'
import json,sqlite3,time
for attempt in range(20):
    try:
        with sqlite3.connect('file:/var/lib/cbot/paper.sqlite?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()
        report=json.loads(row[0])
        if not 0<=time.time()-report['observed_at']<=120: raise ValueError('Waiting for fresh status')
        assert report['account']['live_orders_enabled'] is False
        print('Virtual cash:',report['account']['cash'],'| Live orders:',report['account']['live_orders_enabled'])
        for decision in report['decisions']: print(decision['product_id'],decision['action'],decision.get('reason',''))
        break
    except (sqlite3.Error,TypeError,KeyError,ValueError):
        if attempt==19: print('First paper cycle not ready; inspect cbot-paper logs before assuming readiness.')
        else: time.sleep(1)
PY
