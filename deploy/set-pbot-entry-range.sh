#!/usr/bin/env bash
# Apply the explicit PBot entry policy, preserving financial history.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /var/lib/pbot/OBSERVED-ACTIVE && -f /etc/pbot.env ]]
grep -Fq ' -m trading_bot.observed_paper ' /etc/systemd/system/pbot-paper.service
for name in pbot-paper pbot-status pbot-dashboard pbot-hourly-review shaneathon-health; do
  grep -Eq '^WorkingDirectory=/opt/(pbot|cbot|shaneathon-ops)/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
task_release="/opt/pbot/releases/entry-range-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
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
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/pbot/display-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-hourly-review shaneathon-health; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_done=0
task_migrated=0
restore_display_on_failure() {
  if [[ "$task_done" == 0 ]]; then
    systemctl stop pbot-paper || true
    if [[ "$task_migrated" == 1 ]]; then
      (cd "$task_release"; "$task_release/venv/bin/python" -m trading_bot.entry_limits --ledger /var/lib/pbot/observed-v1.sqlite --rollback) || { echo 'Policy rollback failed; paper engine left stopped.' >&2; return; }
    fi
    for name in pbot-paper pbot-status pbot-dashboard pbot-hourly-review shaneathon-health; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    systemctl daemon-reload
    systemctl restart pbot-paper pbot-status pbot-dashboard || true
    systemctl start pbot-hourly-review.timer || true
    echo 'Prior units/policy restored; financial history preserved.' >&2
  fi
}
trap restore_display_on_failure EXIT
systemctl stop pbot-hourly-review.timer pbot-hourly-review.service
systemctl stop pbot-paper
python3 - "$task_backup/observed.sqlite" <<'PYBACKUP'
import sqlite3,sys
with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as source, sqlite3.connect(sys.argv[1]) as target:
    source.backup(target)
    assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
PYBACKUP
(cd "$task_release"; "$task_release/venv/bin/python" -m trading_bot.entry_limits --ledger /var/lib/pbot/observed-v1.sqlite)
task_migrated=1
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-hourly-review','shaneathon-health'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    path.write_text(text.replace(old,sys.argv[1]))
PY
systemctl daemon-reload
systemctl restart pbot-paper pbot-status pbot-dashboard
(
  set +x
  set -a
  source /etc/pbot.env
  set +a
  cd "$task_release"
  "$task_release/venv/bin/python" - <<'PY'
import os,time
from trading_bot.status_client import read_status,read_trades
from trading_bot.display_status import central
for attempt in range(25):
    try:
        data=read_status('http://127.0.0.1:8765/status',os.environ['PBOT_READ_TOKEN'])
        assert data['operation_mode']=='OBSERVED_BOOK_PAPER' and data['account']['live_orders_enabled'] is False
        assert data['configuration']['version']=='OBSERVED_PAPER_V3_FIXED_150'
        assert data['configuration']['min_trade_cost']=='0.50' and data['configuration']['max_trade_cost']=='1.50'
        assert not data.get('display_health_error') and 'display_health' in data
        for name,report in data['portfolios'].items():
            assert 'activity' in report and 'display_state' in report and 'last_trade' in report['activity']
        history=read_trades('http://127.0.0.1:8765/status',os.environ['PBOT_READ_TOKEN'],wallet=next(iter(data['portfolios'])),as_of=time.time())
        print('Read-only trade history ready:',history['total_filled_trades'],'filled trades in first wallet;',history['page_count'],'page(s).')
        print('Engine update (Central):',central(data['display_health']['engine_updated_at']))
        print('Input update (Central):',central(data['display_health']['input_updated_at']))
        print('Last filled trade (Central):',central(data['display_health']['last_filled_at']))
        for name,report in data['portfolios'].items():
            print(name,'|',report['display_state']['state'],'| last fill:',central(report['activity']['last_filled_at']))
        break
    except Exception as error:
        if attempt==24: raise SystemExit('Display readiness failed: '+type(error).__name__)
        time.sleep(1)
PY
)
systemctl start pbot-hourly-review.service
systemctl start pbot-hourly-review.timer
systemctl is-active --quiet pbot-paper pbot-status pbot-dashboard pbot-hourly-review.timer
task_done=1
echo 'PBot now targets at most $1.50 per new entry including modeled fees, in every wallet.'
echo 'Whole-contract sizing and partial fills may cost less than $1.50. Existing holdings and balances preserved.'
echo 'Current $1.50-policy results separated from earlier entries; history available at https://pbot.shaneathon.com .'
echo 'Hourly review updated for the new cohort; existing wallet pauses and manual stop files preserved.'
echo 'Collectors, Coinbase and input exporter unchanged. Real trading remains disabled.'
