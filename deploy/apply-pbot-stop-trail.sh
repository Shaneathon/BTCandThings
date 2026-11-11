#!/usr/bin/env bash
# PBot-only V7 paper strategy rollout; no CBot services or files touched.
set -euo pipefail
[[ "${1:-}" == "--apply" && "$EUID" == 0 ]] || { echo 'Run as root with --apply'; exit 2; }
src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit=/etc/systemd/system/pbot-paper.service
ledger=/var/lib/pbot/observed-v1.sqlite
[[ -f "$unit" && -f "$ledger" && -f /var/lib/pbot/OBSERVED-ACTIVE ]] || { echo 'PBot prerequisites missing'; exit 3; }
grep -q ' -m trading_bot.band_runner ' "$unit" || { echo 'Unexpected PBot runner'; exit 3; }
old="$(sed -n 's/^WorkingDirectory=//p' "$unit")"
[[ "$old" == /opt/pbot/releases/* && -x "$old/venv/bin/python" ]] || { echo 'Unexpected PBot release'; exit 3; }
release="/opt/pbot/releases/stop-trail-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$release"
for package in trading_bot coinbase_bot coinbase_tracker operations; do
  [[ ! -d "$src/$package" ]] || cp -a "$src/$package" "$release/"
done
find "$release/trading_bot" -type d -name __pycache__ -prune -exec rm -rf {} +
ln -s "$old/venv" "$release/venv"
(cd "$release"; "$release/venv/bin/python" -m unittest discover -s trading_bot/tests -q; "$release/venv/bin/python" trading_bot/smoke_ui.py)
backup="$(mktemp -d /opt/pbot/stop-trail-backup.XXXXXX)"
chmod 700 "$backup"
cp -p "$unit" "$backup/pbot-paper.service"
python3 - "$ledger" "$backup/observed.sqlite" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as source, sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
    assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
PY
echo "PBot-only backup: $backup"
done_ok=0
migrated=0
rollback() {
  if [[ "$done_ok" == 0 ]]; then
    echo 'Deployment failed; restoring PBot unit and paper ledger backup.' >&2
    systemctl stop pbot-paper || true
    if [[ "$migrated" == 1 ]]; then
      (cd "$release"; "$release/venv/bin/python" -m trading_bot.entry_limits --profile market-band --ledger "$ledger" --rollback) || { echo 'Policy rollback failed; PBot left stopped for safety' >&2; return; }
    fi
    cp "$backup/pbot-paper.service" "$unit"
    systemctl daemon-reload
    systemctl start pbot-paper || true
  fi
}
trap rollback EXIT
systemctl stop pbot-paper
(cd "$release"; "$release/venv/bin/python" -m trading_bot.entry_limits --profile market-band --ledger "$ledger")
migrated=1
sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$release|" "$unit"
systemctl daemon-reload
systemctl start pbot-paper
sleep 4
systemctl is-active --quiet pbot-paper
(cd "$release"; "$release/venv/bin/python" - "$ledger" <<'PY'
import json,sqlite3,sys
from trading_bot.market_band import BAND_SETTINGS
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    assert json.loads(db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])==BAND_SETTINGS
    assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
print('PASS: PBot V7 policy and ledger integrity')
PY
)
done_ok=1
trap - EXIT
echo "PASS: PBot paper service V7 running. CBot unchanged. Ledger backup: $backup"
