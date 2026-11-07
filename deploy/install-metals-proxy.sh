#!/usr/bin/env bash
# Add a private sampled spot-proxy feed; never modify Champion or fabricate history.
set -euo pipefail
umask 022
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_install_root="${METALS_INSTALL_ROOT:-/opt/btc-metals-proxy}"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/btc-metals-proxy ]] || { echo 'Apply requires root and standard paths'; exit 2; }
  if systemctl cat btc-metals-proxy.service >/dev/null 2>&1; then echo 'Existing metals service; inspect instead of replacing'; exit 1; fi
  [[ ! -e /var/lib/btc-metals-proxy ]] || { echo 'Existing metals cache; preserve history and inspect'; exit 1; }
  python3 - <<'PY'
import socket
with socket.socket() as sock: sock.bind(('127.0.0.1',8770))
PY
  task_research_unit=/etc/systemd/system/btc-multiasset-research.service
  task_old_research="$(systemctl show btc-multiasset-research.service -p WorkingDirectory --value)"
  [[ -f "$task_research_unit" ]] || { echo 'Expected existing research service'; exit 1; }
  if grep -q 'BTC_METALS_PROXY_URL' "$task_research_unit"; then echo 'Research already has a metals source; inspect before changing'; exit 1; fi
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release/metal_proxy"
cp "$task_source_root"/metal_proxy/*.py "$task_release/metal_proxy/"
(cd "$task_release"; python3 -m unittest metal_proxy.test_service -v)
if [[ "$mode" == --prepare ]]; then echo "METALS PREPARED: $task_release. No services changed."; exit 0; fi
task_log="$(mktemp)"
# Prepare/test the updated reader while every existing collector still runs.
bash "$task_source_root/deploy/install-research.sh" --prepare | tee "$task_log"
task_new_research="$(sed -n 's/^PREPARED: \(\/opt\/btcandthings-research\/releases\/[A-Za-z0-9_-]*\)$/\1/p' "$task_log")"
[[ -f "$task_new_research/collection/unit_update.py" ]] || { echo 'Prepared research release missing'; exit 1; }
task_rendered="$(mktemp)"
python3 "$task_new_research/collection/unit_update.py" --unit "$task_research_unit" --old "$task_old_research" --new "$task_new_research" --out "$task_rendered"
python3 - "$task_rendered" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]);text=path.read_text()
text=text.replace('[Service]\n','[Service]\nEnvironment=BTC_METALS_PROXY_URL=http://127.0.0.1:8770\n',1)
path.write_text(text)
PY
python3 - "$task_release" <<'PY'
import os,sys
text='''[Unit]
Description=Observed gold/silver spot quote proxy (not official settlement)
After=network-online.target
[Service]
DynamicUser=yes
StateDirectory=btc-metals-proxy
StateDirectoryMode=0700
WorkingDirectory=RELEASE
ExecStart=/usr/bin/python3 -m metal_proxy.service --db /var/lib/btc-metals-proxy/quotes.sqlite --port 8770
Restart=on-failure
RestartSec=30
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/btc-metals-proxy
UMask=0077
CPUQuota=10%
MemoryMax=96M
[Install]
WantedBy=multi-user.target
'''.replace('RELEASE',sys.argv[1])
fd=os.open('/etc/systemd/system/btc-metals-proxy.service',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
with os.fdopen(fd,'w') as stream: stream.write(text)
PY
systemctl daemon-reload
systemctl enable --now btc-metals-proxy.service
python3 - <<'PY'
import json,time
from urllib.request import urlopen
for attempt in range(20):
    try:
        with urlopen('http://127.0.0.1:8770/candles?asset=GOLD',timeout=3) as response: data=json.load(response)
        assert data['asset']=='GOLD' and data['is_official_settlement_feed'] is False
        break
    except Exception:
        if attempt==19: raise SystemExit('Metals endpoint unavailable; research remains on the prior unit. Inspect btc-metals-proxy logs.')
        time.sleep(1)
PY
task_backup="$(mktemp /opt/btcandthings-research/metals-unit-backup.XXXXXX)"
cp "$task_research_unit" "$task_backup"
install -m 644 "$task_rendered" "$task_research_unit"
systemctl daemon-reload
task_research_ok=1
if ! systemctl restart btc-multiasset-research.service; then task_research_ok=0; fi
if ! systemctl is-active --quiet btc-multiasset-research.service; then task_research_ok=0; fi
if [[ "$task_research_ok" == 0 ]]; then
  install -m 644 "$task_backup" "$task_research_unit"
  systemctl daemon-reload
  systemctl start btc-multiasset-research.service
  echo 'Research restart failed; prior unit restored. Original Champion/Challenger untouched.' >&2
  exit 1
fi
if [[ -f /etc/systemd/system/shaneathon-health.service ]]; then
  bash "$task_source_root/deploy/update-maintenance.sh" --apply
fi
python3 - <<'PY'
import json
from urllib.request import urlopen
for asset in ('GOLD','SILVER'):
    with urlopen('http://127.0.0.1:8770/candles?asset='+asset,timeout=5) as response: data=json.load(response)
    print(asset,'| completed sampled candles:',data['completed_candles'],'| feed:',data['feed_status'])
print('Private metals proxy installed. Initial warm-up requires at least 50 contiguous completed minutes of actual source updates.')
print('Research reader updated; only the multiasset research service briefly restarted. Champion, Challenger, Coin and both bots were not restarted.')
print('Paper entry readiness still requires current verified contract metadata and fresh predictions. Official settlements remain Chainlink.')
PY
