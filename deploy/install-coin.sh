#!/usr/bin/env bash
# Independent Coinbase research stack. No BTC/bot unit changes or order calls.
set -euo pipefail
umask 022
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
task_install_root="${COIN_INSTALL_ROOT:-/opt/coin}"
task_state_root="${COIN_STATE_ROOT:-/var/lib/coin}"
mode="${1:---prepare}"
if [[ "$mode" != --prepare && "$mode" != --apply ]]; then echo 'Usage: install-coin.sh [--prepare|--apply]' >&2; exit 2; fi
if [[ "$mode" == --apply && ( "$EUID" -ne 0 || "$task_install_root" != /opt/coin || "$task_state_root" != /var/lib/coin ) ]]; then
  echo '--apply requires root and standard /opt/coin, /var/lib/coin paths.' >&2; exit 2
fi
if [[ "$task_install_root" != /* || "$task_state_root" != /* || "$task_install_root" == *' '* || "$task_state_root" == *' '* ]]; then
  echo 'Expected absolute paths with no spaces.' >&2; exit 2
fi
if [[ "$mode" == --apply ]]; then
  for name in coin-collector coin-status coin-dashboard; do
    if systemctl cat "$name.service" >/dev/null 2>&1; then echo "Existing $name.service requires review; refusing replacement." >&2; exit 1; fi
  done
  if [[ -e /etc/coin.env || -L /etc/coin.env ]]; then echo 'Existing /etc/coin.env requires review; refusing replacement.' >&2; exit 1; fi
  if getent passwd coin >/dev/null || getent group coin >/dev/null; then echo 'Existing coin identity requires review; no user changed.' >&2; exit 1; fi
  python3 - <<'PY'
import socket
for port in (8767,8504):
    with socket.socket() as check:
        check.bind(('127.0.0.1',port))
print('Coin API/dashboard ports are available.')
PY
fi
task_release="$task_install_root/releases/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release" "$task_state_root"
python3 "$task_source_root/collection/preflight.py" "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('coinbase_tracker','coinbase_bot','trading_bot'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest)
        dest.chmod(0o644)
frontend=target/'BTCandThings_Website'/'BTCandThings_Upload'
frontend.mkdir(parents=True,exist_ok=True)
for name in ('market_candles.py','tracker_panels.py'):
    shutil.copyfile(source/'BTCandThings_Website'/'BTCandThings_Upload'/name,frontend/name)
    (frontend/name).chmod(0o644)
PY
python3 -m venv "$task_release/venv"
"$task_release/venv/bin/python" -m pip install --disable-pip-version-check -r "$task_source_root/coinbase_tracker/requirements.txt"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s coinbase_tracker/tests -v)
(cd "$task_release"; "$task_release/venv/bin/python" coinbase_tracker/smoke_ui.py)
if [[ "$mode" == --prepare ]]; then
  echo "COIN PREPARED: $task_release"
  echo 'No units, users, credentials or network services created.'
  exit 0
fi
if [[ ! -e "$task_state_root/preflight.sqlite" && -n "${COIN_SEED_DB:-}" ]]; then
  (cd "$task_release"; "$task_release/venv/bin/python" -m coinbase_tracker.storage "$COIN_SEED_DB" "$task_state_root/preflight.sqlite")
fi
(cd "$task_release"; "$task_release/venv/bin/python" -m coinbase_tracker.collector --db "$task_state_root/preflight.sqlite")
if [[ ! -e "$task_state_root/research.sqlite" ]]; then
  (cd "$task_release"; "$task_release/venv/bin/python" -m coinbase_tracker.storage "$task_state_root/preflight.sqlite" "$task_state_root/research.sqlite")
fi
python3 - <<'PY'
import os,secrets
fd=os.open('/etc/coin.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream:
    stream.write('COIN_READ_TOKEN='+secrets.token_hex(32)+'\nCOIN_STATUS_URL=http://127.0.0.1:8767/status\n')
print('Private Coin read token generated; value not displayed.')
PY
useradd --system --user-group --home-dir /var/lib/coin --no-create-home --shell /usr/sbin/nologin coin
chmod 700 "$task_state_root"
chown coin:coin "$task_state_root"
for file in "$task_state_root"/*.sqlite*; do
  if [[ -f "$file" ]]; then chown coin:coin "$file"; chmod 600 "$file"; fi
done
for name in coin-collector coin-status coin-dashboard; do
  python3 - "$task_source_root/coinbase_tracker/deploy/$name.service" "/etc/systemd/system/$name.service" "$task_release" <<'PY'
from pathlib import Path
import os,sys
source,destination=map(Path,sys.argv[1:3])
text=source.read_text().replace('/opt/coin',sys.argv[3])
fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
with os.fdopen(fd,'w') as output: output.write(text)
PY
done
systemctl daemon-reload
systemctl enable --now coin-collector.service coin-status.service coin-dashboard.service
echo "COIN RELEASE: $task_release"
echo 'Coin collector, private API and local dashboard requested. No DNS, public proxy, existing collector or bot changed.'
echo "Validate after its first cycle: cd $task_release && $task_release/venv/bin/python -m coinbase_tracker.collector --db /var/lib/coin/research.sqlite --status"
