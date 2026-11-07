#!/usr/bin/env bash
# Upgrade both PAPER execution adapters. No credentials, DNS or live orders changed.
set -euo pipefail
umask 077
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input cbot-paper cbot-status cbot-dashboard; do
  grep -Eq '^WorkingDirectory=/opt/(pbot|cbot)/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo 'Unexpected bot unit; no changes made'; exit 1; }
done
grep -Fq ' -m trading_bot.dual_sandbox watch ' /etc/systemd/system/pbot-paper.service
grep -Fq ' -m coinbase_bot.runner ' /etc/systemd/system/cbot-paper.service
[[ -f /var/lib/pbot/STOP-SANDBOX && ! -L /var/lib/pbot/STOP-SANDBOX ]]
for file in /var/lib/pbot/observed-v1.sqlite /var/lib/cbot/observed-v1.sqlite /var/lib/pbot/OBSERVED-ACTIVE /var/lib/cbot/OBSERVED-ACTIVE; do
  [[ ! -e "$file" && ! -L "$file" ]] || { echo 'New ledger or marker already exists; preserve it and inspect before reinstalling.'; exit 1; }
done
python3 - <<'PY'
import sqlite3,json
from pathlib import Path
for path in Path('/var/lib/pbot').glob('*directional-v1.sqlite'):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        if any(json.loads(r[0]).get('state')=='PAPER_OPEN' for r in db.execute('SELECT payload FROM positions')):
            raise SystemExit('Old PBot has unsettled positions; let settlements finish before migrating.')
config=json.loads(Path('/etc/cbot-paper.json').read_text())
if config.get('fee_rate')!='0.006': raise SystemExit('Unexpected Coinbase fee estimate; review before migration.')
PY
# Prepare all dependencies and UI/test checks while the current services run.
task_pbot_log="$(mktemp)"
bash "$task_source_root/deploy/start-pbot-sandbox.sh" --prepare | tee "$task_pbot_log"
task_pbot_release="$(sed -n 's/^SANDBOX PREPARED: \(.*\)\. No running services changed\.$/\1/p' "$task_pbot_log")"
task_cbot_log="$(mktemp)"
bash "$task_source_root/deploy/install-cbot.sh" --prepare | tee "$task_cbot_log"
task_cbot_release="$(sed -n 's/^CBOT PREPARED: \(.*\)\. No services or users created\.$/\1/p' "$task_cbot_log")"
[[ "$task_pbot_release" == /opt/pbot/releases/* && "$task_cbot_release" == /opt/cbot/releases/* ]]
mkdir -m 755 "$task_pbot_release/operations"
cp "$task_source_root"/operations/*.py "$task_pbot_release/operations/"
chmod 644 "$task_pbot_release"/operations/*.py
(cd "$task_pbot_release"; python3 -m unittest operations.test_maintenance -q)
task_backup="$(mktemp -d /opt/pbot/observed-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input cbot-paper cbot-status cbot-dashboard shaneathon-health; do
  cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"
done
(
  cd "$task_source_root"
  python3 - "$task_pbot_release" "$task_cbot_release" <<'PYCODE'
from pathlib import Path
import sys
from trading_bot.observed_units import render
pbot,cbot=sys.argv[1:]
updates={}
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-sandbox-input','cbot-paper','cbot-status','cbot-dashboard','shaneathon-health'):
    path=Path('/etc/systemd/system')/(name+'.service')
    updates[path]=render(name,path.read_text(),pbot,cbot)
# Validate every unit before writing any of them.
for path,text in updates.items(): path.write_text(text)
PYCODE
)
systemctl daemon-reload
task_ok=1
if ! systemctl restart pbot-sandbox-input.service pbot-paper.service pbot-status.service pbot-dashboard.service cbot-paper.service cbot-status.service cbot-dashboard.service; then task_ok=0; fi
if [[ "$task_ok" == 1 ]]; then
  if ! python3 - <<'PY'
import json,sqlite3,time
from pathlib import Path
for attempt in range(30):
    try:
        for folder,mode in [('pbot','OBSERVED_BOOK_PAPER'),('cbot','OBSERVED_LIMIT_PAPER')]:
            path=Path('/var/lib')/folder/'observed-v1.sqlite'
            with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
            report=json.loads(row[1])
            assert 0<=time.time()-row[0]<30 and report['operation_mode']==mode
            assert report['account']['live_orders_enabled'] is False
        break
    except (sqlite3.Error,TypeError,KeyError,AssertionError):
        if attempt==29: raise SystemExit('New paper engine readiness not established')
        time.sleep(1)
PY
  then task_ok=0; fi
fi
if [[ "$task_ok" == 0 ]]; then
  for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input cbot-paper cbot-status cbot-dashboard shaneathon-health; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
  systemctl daemon-reload
  systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service cbot-paper.service cbot-status.service cbot-dashboard.service
  echo 'Readiness failed; old service units restored. All ledgers preserved, fixed-price PBot remains paused.' >&2
  exit 1
fi
# Health checks select the new ledgers only after both have proved ready.
install -m 640 -o root -g pbot /dev/null /var/lib/pbot/OBSERVED-ACTIVE
install -m 640 -o root -g cbot /dev/null /var/lib/cbot/OBSERVED-ACTIVE
systemctl start --no-block shaneathon-health.service
python3 - <<'PY'
import json,sqlite3
for name in ('pbot','cbot'):
    with sqlite3.connect('file:/var/lib/'+name+'/observed-v1.sqlite?mode=ro',uri=True) as db:
        report=json.loads(db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()[0])
    print(name.upper(),report['operation_mode'],'| live orders:',report['account']['live_orders_enabled'])
    if name=='pbot':
        print('Input:',report['input_status'])
        for wallet,state in report['portfolios'].items():
            print(wallet,'| cash:',state['account']['cash'],'| orders:',state['order_states'],
                  '| latest:',state['decisions'][0]['reason'] if state['decisions'] else 'WAITING_FOR_ENTRY_WINDOW')
    else: print('Orders:',report['order_states'],'| fee basis:',report['fee_basis'])
PY
echo 'Both paper engines now use separate observed-price ledgers. Old histories are preserved.'
echo 'Each new wallet starts at virtual $1,000. Old Coinbase virtual positions remain archived in the old ledger.'
echo 'PBot uses the support-reported 0.06 fee schedule; API coefficient differences remain visible per position.'
echo 'CBot fees remain estimated pending an actual account fee tier. Sampled books cannot guarantee live fills.'
echo 'Collectors, account credentials, DNS, and all live-order interlocks were preserved.'
echo 'Dashboards: https://pbot.shaneathon.com and https://cbot.shaneathon.com'
