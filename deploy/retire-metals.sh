#!/usr/bin/env bash
# Retire active metals collection and wallets; never delete historical data.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - <<'PY'
import json,sqlite3
with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
    for payload, in db.execute("SELECT payload FROM positions WHERE wallet IN ('GOLD_15m','SILVER_15m')"):
        assert json.loads(payload)['state']!='PAPER_OPEN','Metals position remains open; preserve and settle before retiring.'
    assert not db.execute("SELECT 1 FROM orders WHERE wallet IN ('GOLD_15m','SILVER_15m') AND state='PROPOSED'").fetchone(),'Pending metals order: inspect before retiring.'
PY
task_names=(pbot-paper pbot-status pbot-dashboard pbot-sandbox-input btc-multiasset-research shaneathon-health)
for name in "${task_names[@]}"; do
  grep -Eq '^WorkingDirectory=/opt/(pbot|cbot|btcandthings-research|shaneathon-ops)/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/pbot-paper.service)"
task_release="/opt/pbot/releases/crypto-only-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('trading_bot','coinbase_bot','coinbase_tracker','collection','operations'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
folder=Path('BTCandThings_Website/BTCandThings_Upload')
for name in ('market_workspace.py','market_board.py','market_candles.py','tracker_panels.py','market_history.py'):
    dest=target/folder/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/folder/name,dest)
PY
ln -s "$task_old/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s trading_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s collection -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
(cd "$task_release"; "$task_release/venv/bin/python" trading_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/pbot/retire-metals-units.XXXXXX)"
chmod 700 "$task_backup"
for name in "${task_names[@]}"; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_sampler_active=0; systemctl is-active --quiet btc-metals-proxy && task_sampler_active=1
task_sampler_enabled=0; systemctl is-enabled --quiet btc-metals-proxy && task_sampler_enabled=1
task_marker=/var/lib/shaneathon-ops/METALS-RETIRED
task_marker_existed=0; [[ ! -e "$task_marker" ]] || task_marker_existed=1
task_done=0
restore_on_failure() {
  if [[ "$task_done" == 0 ]]; then
    for name in "${task_names[@]}"; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    [[ "$task_marker_existed" == 1 ]] || rm -f "$task_marker"
    systemctl daemon-reload
    systemctl restart btc-multiasset-research pbot-paper pbot-status pbot-dashboard || true
    systemctl start pbot-sandbox-input.timer || true
    if [[ "$task_sampler_enabled" == 1 ]]; then systemctl enable btc-metals-proxy || true; fi
    if [[ "$task_sampler_active" == 1 ]]; then systemctl start btc-metals-proxy || true; fi
    echo 'Prior units restored. Ledgers and historical data preserved.' >&2
  fi
}
trap restore_on_failure EXIT
systemctl stop pbot-sandbox-input.timer pbot-sandbox-input.service
python3 - "$task_release" "${task_names[@]}" <<'PY'
from pathlib import Path
import sys
for name in sys.argv[2:]:
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    text=text.replace(old,sys.argv[1])
    if name=='btc-multiasset-research':
        text='\n'.join(line for line in text.splitlines() if not line.startswith('Environment=BTC_METALS_PROXY_URL='))+'\n'
    path.write_text(text)
PY
install -m 600 /dev/null "$task_marker"
systemctl daemon-reload
systemctl restart btc-multiasset-research
systemctl start pbot-sandbox-input.service
systemctl restart pbot-paper pbot-status pbot-dashboard
systemctl start pbot-sandbox-input.timer
python3 - <<'PY'
import sqlite3,json,time
expected={a+'_'+d for a in ('BTC','ETH','XRP','SOL') for d in ('5m','15m')}
for attempt in range(120):
    try:
        with sqlite3.connect('file:/var/lib/btcandthings-research/research.sqlite?mode=ro',uri=True) as db:
            stamp,payload=db.execute('SELECT observed_at,payload FROM collector_status WHERE singleton=1').fetchone()
        data=json.loads(payload)
        assert set(data['streams'])==expected and 0<=time.time()-stamp<240
        with sqlite3.connect('file:/var/lib/pbot/observed-v1.sqlite?mode=ro',uri=True) as db:
            stamp,payload=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
        bot=json.loads(payload)
        assert set(bot['portfolios'])==expected|{'Champion','Challenger B'}
        assert time.time()-stamp<20 and bot['input_status']=='FRESH'
        assert bot['account']['live_orders_enabled'] is False
        assert bot['configuration']['max_trade_cost']=='5'
        break
    except (AssertionError,KeyError,TypeError,sqlite3.Error):
        if attempt==119: raise SystemExit('Crypto-only readiness not established')
        time.sleep(1)
print('Verified eight collector streams and ten active paper wallets. $5 cap preserved; live orders disabled.')
PY
if systemctl cat btc-metals-proxy.service >/dev/null 2>&1; then systemctl disable --now btc-metals-proxy.service; fi
systemctl is-active --quiet btc-multiasset-research pbot-paper pbot-status pbot-dashboard
task_done=1
systemctl start --no-block shaneathon-health.service || true
echo 'Gold/silver removed from active research collection and PBot; sampler disabled. All history and balances preserved.'
echo 'BTC Champion/Challenger collectors and Coinbase services unchanged. Refresh PBot.'
echo 'Tracker selector source updated in GitHub; separately hosted Streamlit must use this branch to receive it.'
