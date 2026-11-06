#!/usr/bin/env bash
# Preserve raw history; update/restart only the independent recorder.
set -euo pipefail
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:---plan}"
[[ "$mode" == --plan || "$mode" == --apply ]] || { echo 'Use --plan or --apply'; exit 2; }
task_unit=/etc/systemd/system/coinbase-recorder.service
if [[ "$mode" == --apply ]]; then
  [[ "$EUID" == 0 && -f "$task_unit" ]] || { echo 'Expected existing recorder unit as root'; exit 2; }
  grep -Eq '^WorkingDirectory=/opt/coinbase-recorder/releases/[A-Za-z0-9_-]+$' "$task_unit" || { echo 'Unexpected recorder release'; exit 1; }
  grep -Fq ' -m market_capture.coinbase_ws --state /var/lib/coinbase-recorder' "$task_unit" || { echo 'Unexpected recorder command'; exit 1; }
fi
task_log="$(mktemp)"
bash "$task_source_root/deploy/install-market-capture.sh" --prepare | tee "$task_log"
task_release="$(sed -n 's/^CAPTURE PREPARED: \(.*\)\. No service installed\.$/\1/p' "$task_log")"
[[ -f "$task_release/market_capture/coinbase_ws.py" ]] || { echo 'Prepared release missing'; exit 1; }
if [[ "$mode" == --plan ]]; then echo 'Recorder update prepared; no process changed.'; exit 0; fi
[[ "$task_release" == /opt/coinbase-recorder/releases/* ]] || { echo 'Expected standard release path'; exit 1; }
task_backup="$(mktemp /opt/coinbase-recorder/unit-backup.XXXXXX)"
cp "$task_unit" "$task_backup"
python3 - "$task_unit" "$task_release" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]);text=path.read_text()
old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
path.write_text(text.replace(old,sys.argv[2]))
PY
systemctl daemon-reload
if ! systemctl restart coinbase-recorder.service; then
  cp "$task_backup" "$task_unit"
  systemctl daemon-reload
  systemctl start coinbase-recorder.service
  echo 'Recorder startup failed; prior unit restored. Archives preserved.' >&2
  exit 1
fi
python3 - <<'PY'
from pathlib import Path
import json,time
path=Path('/var/lib/coinbase-recorder/status.json')
for attempt in range(30):
    if path.exists():
        report=json.loads(path.read_text())
        if (report.get('configured_channels')==['heartbeats','market_trades']
                and report.get('state')=='CAPTURING_RAW'
                and report.get('channels',{}).get('heartbeats',0)>0
                and report.get('channels',{}).get('market_trades',0)>0):
            print(json.dumps(report,indent=2));break
    if attempt==29:
        print('Both working channels have not been confirmed yet; current status:')
        if path.exists(): print(path.read_text())
    else: time.sleep(1)
print('Only the raw recorder was restarted. All archives, bots and existing collectors preserved.')
PY
