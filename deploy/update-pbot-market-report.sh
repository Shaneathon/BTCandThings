#!/usr/bin/env bash
# P/L presentation update only. Fixed-price entries remain paused.
set -euo pipefail
umask 077
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do
  grep -Eq '^WorkingDirectory=/opt/pbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo 'Unexpected PBot unit; no changes made'; exit 1; }
done
grep -Fq ' -m trading_bot.dual_sandbox watch ' /etc/systemd/system/pbot-paper.service || { echo 'Unexpected engine; no changes made'; exit 1; }
[[ -f /var/lib/pbot/STOP-SANDBOX && ! -L /var/lib/pbot/STOP-SANDBOX ]] || { echo 'Run the realism preparation first; expected fixed-price entries to be paused.'; exit 1; }
task_log="$(mktemp)"
bash "$task_source_root/deploy/start-pbot-sandbox.sh" --prepare | tee "$task_log"
task_release="$(sed -n 's/^SANDBOX PREPARED: \(.*\)\. No running services changed\.$/\1/p' "$task_log")"
[[ "$task_release" == /opt/pbot/releases/* && -f "$task_release/trading_bot/market_pnl.py" ]] || { echo 'Prepared release not found'; exit 1; }
task_backup="$(mktemp -d /opt/pbot/market-report-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-sandbox-input'):
    path=Path('/etc/systemd/system')/(name+'.service')
    text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    path.write_text(text.replace(old,sys.argv[1]))
PY
systemctl daemon-reload
task_ok=1
if ! systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service; then task_ok=0; fi
for name in pbot-paper pbot-status pbot-dashboard; do
  if ! systemctl is-active --quiet "$name.service"; then task_ok=0; fi
done
if [[ "$task_ok" == 0 ]]; then
  for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
  systemctl daemon-reload
  systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service
  echo 'Prior units restored after startup failure; fixed-price entries remain paused.' >&2
  exit 1
fi
cd "$task_release"
"$task_release/venv/bin/python" -m trading_bot.market_pnl --state /var/lib/pbot
echo 'Per-market complete-ledger P/L is installed: https://pbot.shaneathon.com'
echo 'These are the OLD fixed-price results, not live-equivalent profits. New entries remain paused.'
echo 'Shared order specification and depth simulator are prepared and tested but not activated.'
echo 'Remaining: verify provider direction mapping, short conversion and actual fee formula before new paper fills.'
echo 'Existing collectors, Coinbase and ledgers were preserved. No live trading.'
