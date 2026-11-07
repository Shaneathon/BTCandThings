#!/usr/bin/env bash
# Paper-only hourly loss review. Never changes models, cash, or live adapters.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for name in pbot-hourly-review.service pbot-hourly-review.timer; do
  [[ ! -e "/etc/systemd/system/$name" ]] || { echo 'Hourly review is already installed; inspect instead of overwriting.'; exit 1; }
done
task_names=(pbot-paper pbot-status pbot-dashboard shaneathon-health)
for name in "${task_names[@]}"; do
  grep -Eq '^WorkingDirectory=/opt/(pbot|cbot|shaneathon-ops)/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
task_release="/opt/pbot/releases/hourly-review-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('trading_bot','coinbase_bot','coinbase_tracker','operations'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
ln -s "$task_old/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/pbot/hourly-review-units.XXXXXX)"
chmod 700 "$task_backup"
for name in "${task_names[@]}"; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_done=0
restore_on_failure() {
  if [[ "$task_done" == 0 ]]; then
    systemctl disable --now pbot-hourly-review.timer >/dev/null 2>&1 || true
    systemctl stop pbot-hourly-review.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/pbot-hourly-review.service /etc/systemd/system/pbot-hourly-review.timer
    for name in "${task_names[@]}"; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    systemctl daemon-reload
    systemctl restart pbot-paper pbot-status pbot-dashboard || true
    echo 'Prior units restored. Financial history and review records preserved.' >&2
  fi
}
trap restore_on_failure EXIT
python3 - "$task_release" "${task_names[@]}" <<'PY'
from pathlib import Path
import os,sys
release=sys.argv[1]
for name in sys.argv[2:]:
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    path.write_text(text.replace(old,release))
service=f'''[Unit]
Description=PBot hourly paper-only loss review
After=pbot-paper.service
[Service]
Type=oneshot
User=pbot
Group=pbot
WorkingDirectory={release}
ExecStart={release}/venv/bin/python -m trading_bot.automatic_review --ledger /var/lib/pbot/observed-v1.sqlite
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/pbot
RestrictAddressFamilies=AF_UNIX
UMask=0077
CPUQuota=10%
MemoryMax=192M
TimeoutStartSec=120
'''
timer='''[Unit]
Description=Review PBot paper results every hour
[Timer]
OnCalendar=hourly
Persistent=true
AccuracySec=1min
Unit=pbot-hourly-review.service
[Install]
WantedBy=timers.target
'''
for name,text in (('service',service),('timer',timer)):
    fd=os.open('/etc/systemd/system/pbot-hourly-review.'+name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    with os.fdopen(fd,'w') as stream: stream.write(text)
PY
systemctl daemon-reload
systemctl restart pbot-paper pbot-status pbot-dashboard
python3 - <<'PY'
import sqlite3,json,time
for attempt in range(30):
    try:
        with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
            stamp,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        data=json.loads(payload)
        assert 'automatic_review' in data and 0<=time.time()-stamp<20
        assert data['account']['live_orders_enabled'] is False
        assert data['configuration']['max_trade_cost']=='5' and data['input_status']=='FRESH'
        break
    except (AssertionError,KeyError,sqlite3.Error):
        if attempt==29: raise SystemExit('New paper engine readiness not established')
        time.sleep(1)
PY
systemctl start pbot-hourly-review.service
systemctl enable --now pbot-hourly-review.timer
systemctl is-active --quiet pbot-paper pbot-status pbot-dashboard pbot-hourly-review.timer
task_done=1
systemctl start --no-block shaneathon-health.service || true
(cd "$task_release"; "$task_release/venv/bin/python" - <<'PY'
import sqlite3
from trading_bot.automatic_review import latest
from trading_bot.display_status import central
with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db: report=latest(db)
print('Hourly paper review installed. Last review:',central(report['reviewed_at']))
for r in report['wallets']:
    print(r['wallet'],'|',r['status'],'| eligible settled trades:',r['closed_trades'],'| net:',r['net_pnl'])
PY
)
echo 'PBot dashboard now shows hourly reviews and any automatic entry pauses. Initial review completed; subsequent reviews run hourly.'
echo 'Only new paper entries may be paused. Existing positions settle normally; wallet balances/history, models and $0.50–$5 limits preserved.'
echo 'Collectors, Coinbase and input exporter unchanged. Real trading stays disabled.'
