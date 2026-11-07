#!/usr/bin/env bash
# Probe fresh public books before updating only PBot request construction.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /var/lib/pbot/OBSERVED-ACTIVE && -f /var/lib/pbot/observed-v1.sqlite ]]
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do
  grep -Eq '^WorkingDirectory=/opt/pbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
grep -Fq ' -m trading_bot.observed_paper ' /etc/systemd/system/pbot-paper.service
task_old_release="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
# One public GET. A skipped cooldown or failed freshness check leaves services as-is.
(cd "$task_source_root"; /root/BTCandThings/venv/bin/python -m trading_bot.verify_runtime --cache-probe --wait-for-budget)
task_release="/opt/pbot/releases/cache-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('trading_bot','coinbase_bot'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
# Reuse the installed dependencies; old release/venv is never edited.
ln -s "$task_old_release/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/pbot/cache-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-sandbox-input'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    path.write_text(text.replace(old,sys.argv[1]))
PY
systemctl daemon-reload
task_ok=1
if ! systemctl restart pbot-paper pbot-status pbot-dashboard; then task_ok=0; fi
if [[ "$task_ok" == 1 ]]; then
  if ! python3 - <<'PY'
import json,sqlite3,time
for attempt in range(20):
    try:
        with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
            row=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        report=json.loads(row[1])
        assert 0<=time.time()-row[0]<10 and report['operation_mode']=='OBSERVED_BOOK_PAPER'
        assert report['account']['live_orders_enabled'] is False
        print('PBot ready; input:',report['input_status'],'| live orders:',report['account']['live_orders_enabled'])
        break
    except (sqlite3.Error,TypeError,KeyError,AssertionError):
        if attempt==19: raise SystemExit(1)
        time.sleep(1)
PY
  then task_ok=0; fi
fi
if [[ "$task_ok" == 0 ]]; then
  for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
  systemctl daemon-reload
  systemctl restart pbot-paper pbot-status pbot-dashboard
  echo 'Prior PBot units restored after readiness failure. Ledger unchanged.' >&2
  exit 1
fi
echo 'Fresh-book request fix installed. Five-second freshness checks, risk rules, ledger and balances preserved.'
echo 'Coinbase and collectors were not restarted. No real trading.'
