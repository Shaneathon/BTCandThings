#!/usr/bin/env bash
# Independent public Coinbase raw recorder. No account keys or order imports.
set -euo pipefail
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_install_root="${CAPTURE_INSTALL_ROOT:-/opt/coinbase-recorder}"
mode="${1:---prepare}"
[[ "$mode" == --prepare || "$mode" == --apply ]] || { echo 'Use --prepare or --apply'; exit 2; }
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && "$task_install_root" == /opt/coinbase-recorder ]] || { echo 'Apply requires root and standard paths'; exit 2; }
  if systemctl cat coinbase-recorder.service >/dev/null 2>&1; then echo 'Existing recorder; refusing replacement'; exit 1; fi
  [[ ! -e /var/lib/coinbase-recorder ]] || { echo 'Existing capture state; inspect before installation'; exit 1; }
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 "$task_source_root/collection/preflight.py" "$task_release"
mkdir "$task_release/market_capture"
cp "$task_source_root"/market_capture/*.py "$task_release/market_capture/"
python3 -m venv "$task_release/venv"
"$task_release/venv/bin/python" -m pip install --disable-pip-version-check -r "$task_source_root/market_capture/requirements.txt"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest market_capture.test_capture -v)
if [[ "$mode" == --prepare ]]; then echo "CAPTURE PREPARED: $task_release. No service installed."; exit 0; fi
python3 - "$task_release" <<'PY'
import os,sys
release=sys.argv[1]
unit='''[Unit]
Description=Public Coinbase raw market-data recorder (no trading)
After=network-online.target
[Service]
DynamicUser=yes
StateDirectory=coinbase-recorder
StateDirectoryMode=0700
WorkingDirectory=RELEASE
ExecStart=RELEASE/venv/bin/python -m market_capture.coinbase_ws --state /var/lib/coinbase-recorder
Restart=on-failure
RestartSec=60
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/coinbase-recorder
UMask=0077
CPUQuota=15%
MemoryMax=256M
Nice=10
[Install]
WantedBy=multi-user.target
'''.replace('RELEASE',release)
fd=os.open('/etc/systemd/system/coinbase-recorder.service',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
with os.fdopen(fd,'w') as output: output.write(unit)
PY
systemctl daemon-reload
systemctl enable --now coinbase-recorder.service
echo 'Public raw recorder installed with CPU/memory and archive budgets. Existing collectors/bots unchanged.'
echo 'Subscription availability must be confirmed by its actual status; raw capture is not a validated tradable book.'
python3 - <<'PY'
from pathlib import Path
import json,time
path=Path('/var/lib/coinbase-recorder/status.json')
for attempt in range(20):
    if path.exists():
        data=json.loads(path.read_text())
        if data.get('session_messages',0)>0 or data.get('state')=='DISCONNECTED_OR_CHANNEL_UNAVAILABLE' or attempt==19:
            print(json.dumps(data,indent=2));break
    if attempt==19: print('Status not ready; inspect coinbase-recorder.service logs.')
    else: time.sleep(1)
PY
