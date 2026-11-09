#!/usr/bin/env bash
# Preserve all history; only BTC15 receives new collection and PBot entries.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_release="/opt/pbot/releases/btc15-$(date -u +%Y%m%dT%H%M%S)-$$"
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
[[ "$task_old" == /opt/pbot/releases/* && -x "$task_old/venv/bin/python" ]]
mkdir -p "$task_release"
python3 - "$task_source" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for folder in ('trading_bot','coinbase_bot','coinbase_tracker','collection','operations','tools','BTCandThings_Website/BTCandThings_Upload'):
    for item in (source/folder).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(item,dest)
PY
ln -s "$task_old/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s collection -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
task_backup="$(mktemp -d /opt/pbot/btc15-units.XXXXXX)"
chmod 700 "$task_backup"
task_names=(pbot-paper pbot-status pbot-dashboard pbot-sandbox-input pbot-hourly-review btc-multiasset-research shaneathon-health)
for name in "${task_names[@]}"; do
  cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"
  [[ ! -d "/etc/systemd/system/$name.service.d" ]] || cp -a "/etc/systemd/system/$name.service.d" "$task_backup/"
done
task_done=0
task_marker_existed=0
[[ ! -f /var/lib/shaneathon-ops/BTC15-ONLY ]] || task_marker_existed=1
restore_scope() {
  if [[ "$task_done" == 0 ]]; then
    for name in "${task_names[@]}"; do
      cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"
      rm -f "/etc/systemd/system/$name.service.d/btc15-scope.conf"
      [[ ! -d "$task_backup/$name.service.d" ]] || cp -a "$task_backup/$name.service.d/." "/etc/systemd/system/$name.service.d/"
    done
    [[ "$task_marker_existed" == 1 ]] || rm -f /var/lib/shaneathon-ops/BTC15-ONLY
    systemctl daemon-reload
    systemctl restart btc-multiasset-research pbot-paper pbot-status pbot-dashboard || true
    systemctl start pbot-sandbox-input.timer || true
    echo 'Scope verification failed; previous units restored. Historical data preserved.' >&2
  fi
}
trap restore_scope EXIT
# Stop pending BUY completion before changing the scope; exits resume with engine.
systemctl stop pbot-paper pbot-sandbox-input.timer pbot-sandbox-input.service btc-multiasset-research
python3 - "$task_release" "${task_names[@]}" <<'PY'
from pathlib import Path
import sys
for name in sys.argv[2:]:
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    if not old.startswith('/opt/'): raise ValueError('Unexpected working directory')
    path.write_text(text.replace(old,sys.argv[1]))
    folder=Path(str(path)+'.d');folder.mkdir(exist_ok=True)
    (folder/'btc15-scope.conf').write_text('[Service]\nEnvironment=SHANEATHON_BTC15_ONLY=1\n')
PY
install -d -m 700 /var/lib/shaneathon-ops
touch /var/lib/shaneathon-ops/BTC15-ONLY
systemctl daemon-reload
systemctl restart btc-multiasset-research
systemctl start pbot-sandbox-input.service
systemctl start pbot-sandbox-input.timer
systemctl restart pbot-paper pbot-status pbot-dashboard
systemctl start --no-block shaneathon-health.service
python3 - <<'PY'
import sqlite3,json,time
for attempt in range(50):
    with sqlite3.connect('file:/var/lib/btcandthings-research/research.sqlite?mode=ro',uri=True) as db:
        stamp,payload=db.execute('SELECT observed_at,payload FROM collector_status WHERE singleton=1').fetchone()
    d=json.loads(payload)
    if set(d['streams'])=={'BTC_15m'} and 0<=time.time()-stamp<180: break
    if attempt==49: raise SystemExit('BTC15 collection not yet verified; inspect service journal. Entry scope is still restricted.')
    time.sleep(1)
with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
    stamp,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
    bot=json.loads(payload)
    assert time.time()-stamp<30 and bot['account']['live_orders_enabled'] is False
    assert bot['input_status']=='FRESH' and bot['configuration']['max_trade_cost']=='1.50'
print('BTC15 collection confirmed. Champion, Challenger B and BTC15 research entries only; $1.50 cap unchanged.')
print('Other Polymarket positions retain exit/settlement handling; other Coinbase wallets frozen and preserved.')
PY
task_done=1
# Coinbase balances/holdings are frozen and retained, never fabricated liquidations.
for name in coin-collector coin-status coin-dashboard coinbase-recorder cbot-paper cbot-status cbot-dashboard cbot-fee-filter-paper; do
  if systemctl cat "$name.service" >/dev/null 2>&1; then systemctl disable --now "$name.service"; fi
done
systemctl start --no-block shaneathon-health.service
# Read-only audit. Keep a failed export separate from the successful scope change.
(
  set -a
  source /root/BTCandThings/collector/.env
  set +a
  cd "$task_release/tools"
  "$task_release/venv/bin/python" bitcoin_review.py --research-db /var/lib/btcandthings-research/research.sqlite --out "/root/btc15-review-$(date -u +%Y%m%dT%H%M%S).json"
) || echo 'Scope applied; read-only review failed. Send this output for diagnosis; no prediction changes made.'
echo "Unit backups: $task_backup . All historical data retained. Real trading disabled."
