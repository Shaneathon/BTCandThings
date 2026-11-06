#!/usr/bin/env bash
# Preserve BTC control ledgers; add separate market-local hypothetical wallets.
set -euo pipefail
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---plan}"
[[ "$mode" == --plan || "$mode" == --apply ]] || { echo 'Use --plan or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 ]] || { echo 'Apply requires root'; exit 2; }
  for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do
    [[ -f "/etc/systemd/system/$name.service" ]] || { echo "Missing $name.service"; exit 1; }
    grep -Eq '^WorkingDirectory=/opt/pbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service" || { echo 'Unexpected PBot release path'; exit 1; }
  done
  grep -Fq ' -m trading_bot.dual_sandbox watch ' /etc/systemd/system/pbot-paper.service || { echo 'Expected existing dual sandbox'; exit 1; }
  if grep -q -- '--all-markets' /etc/systemd/system/pbot-paper.service; then echo 'All-market mode already installed; preserve ledgers and inspect current status instead of reinstalling.'; exit 1; fi
fi
task_log="$(mktemp)"
bash "$task_source_root/deploy/start-pbot-sandbox.sh" --prepare | tee "$task_log"
task_release="$(sed -n 's/^SANDBOX PREPARED: \(.*\)\. No running services changed\.$/\1/p' "$task_log")"
[[ -n "$task_release" && -f "$task_release/trading_bot/dual_sandbox.py" ]] || { echo 'Prepared release not found'; exit 1; }
if [[ "$mode" == --plan ]]; then echo 'All-market update prepared; no running services changed.'; exit 0; fi
[[ "$task_release" == /opt/pbot/releases/* ]] || { echo 'Apply requires standard release paths'; exit 1; }
(
  set +x
  set -a
  source /root/BTCandThings/collector/.env
  set +a
  cd "$task_release"
  "$task_release/venv/bin/python" -m trading_bot.dual_sandbox export --source /var/lib/btcandthings-research/research.sqlite --input /var/lib/pbot-input/dual-sandbox.json --group "$(id -g pbot)" --all-markets
)
task_backup="$(mktemp -d /opt/pbot/all-market-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
python3 - "$task_release" <<'PY'
from pathlib import Path
import sys
release=sys.argv[1]
for name in ('pbot-paper','pbot-status','pbot-dashboard','pbot-sandbox-input'):
    path=Path('/etc/systemd/system')/(name+'.service')
    text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    text=text.replace(old,release)
    if name in ('pbot-paper','pbot-sandbox-input'):
        text='\n'.join(line+' --all-markets' if line.startswith('ExecStart=') else line for line in text.splitlines())+'\n'
    path.write_text(text)
PY
systemctl daemon-reload
task_ok=1
if ! systemctl restart pbot-sandbox-input.service pbot-paper.service pbot-status.service pbot-dashboard.service; then task_ok=0; fi
for name in pbot-paper pbot-status pbot-dashboard; do
  if ! systemctl is-active --quiet "$name.service"; then task_ok=0; fi
done
if [[ "$task_ok" == 0 ]]; then
  for name in pbot-paper pbot-status pbot-dashboard pbot-sandbox-input; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
  systemctl daemon-reload
  systemctl restart pbot-paper.service pbot-status.service pbot-dashboard.service
  echo 'PBot update failed immediate startup; prior units restored. All ledger files preserved.' >&2
  exit 1
fi
python3 - <<'PY'
import json,sqlite3,time
for attempt in range(20):
    try:
        with sqlite3.connect('file:/var/lib/pbot/comparison.sqlite?mode=ro',uri=True) as db:
            row=db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()
        report=json.loads(row[0])
        if len(report.get('market_portfolios',{}))!=10: raise ValueError('Awaiting first all-market cycle')
        print('PBOT ALL-MARKET DIRECTIONAL SANDBOX: 10 independent research slots; original BTC control ledgers preserved.')
        for name,state in report['market_portfolios'].items():
            print(name,state['coverage_status'],'| entries:',state['account']['position_count'],
                  '| live orders:',state['account']['live_orders_enabled'])
        print('Prices remain hypothetical, not executable fills. CBot already covers all four Coinbase products.')
        print('Collectors, Coinbase services, DNS and portal protection were not changed.')
        break
    except (sqlite3.Error,TypeError,KeyError,ValueError):
        if attempt==19: print('Services started; first all-market status not ready. Inspect pbot-paper logs.')
        else: time.sleep(1)
PY
