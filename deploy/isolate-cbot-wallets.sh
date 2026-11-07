#!/usr/bin/env bash
# Preserve history and cash; split each strategy's paper capital/risk four ways.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for path in /var/lib/cbot/products /var/lib/cbot/product-baseline.sqlite /var/lib/cbot/product-fee-filter.sqlite /var/lib/cbot/PRODUCT-WALLETS-ACTIVE; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo 'Isolated wallet state already exists; preserve it and inspect rather than reinstalling.'; exit 1; }
done
for name in cbot-paper cbot-fee-filter-paper cbot-status cbot-dashboard; do
  grep -Eq '^WorkingDirectory=/opt/cbot/releases/[A-Za-z0-9_-]+$' "/etc/systemd/system/$name.service"
done
grep -Fq -- '--ledger /var/lib/cbot/observed-v1.sqlite' /etc/systemd/system/cbot-paper.service
grep -Fq -- '--ledger /var/lib/cbot/fee-filter-v1.sqlite' /etc/systemd/system/cbot-fee-filter-paper.service
systemctl is-active --quiet cbot-paper cbot-fee-filter-paper
task_old="$(sed -n 's/^WorkingDirectory=//p' /etc/systemd/system/cbot-paper.service)"
task_release="/opt/cbot/releases/wallets-$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$task_release"
python3 - "$task_source_root" "$task_release" <<'PY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
for package in ('coinbase_bot','coinbase_tracker','trading_bot','operations'):
    for item in (source/package).rglob('*.py'):
        if '__pycache__' in item.parts: continue
        dest=target/item.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item,dest);dest.chmod(0o644)
PY
ln -s "$task_old/venv" "$task_release/venv"
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest discover -s coinbase_bot/tests -q)
(cd "$task_release"; "$task_release/venv/bin/python" -m unittest operations.test_maintenance -q)
(cd "$task_release"; "$task_release/venv/bin/python" coinbase_bot/smoke_ui.py)
task_backup="$(mktemp -d /opt/cbot/wallet-unit-backup.XXXXXX)"
chmod 700 "$task_backup"
for name in cbot-paper cbot-fee-filter-paper cbot-status cbot-dashboard shaneathon-health shaneathon-backup; do cp "/etc/systemd/system/$name.service" "$task_backup/$name.service"; done
task_committed=0
restore_on_failure() {
  if [[ "$task_committed" == 0 ]]; then
    systemctl stop cbot-paper cbot-fee-filter-paper || true
    for name in cbot-paper cbot-fee-filter-paper cbot-status cbot-dashboard shaneathon-health shaneathon-backup; do cp "$task_backup/$name.service" "/etc/systemd/system/$name.service"; done
    rm -f /var/lib/cbot/PRODUCT-WALLETS-ACTIVE
    systemctl daemon-reload
    systemctl restart cbot-paper cbot-fee-filter-paper cbot-status cbot-dashboard || true
    echo 'Prior units restored after failure. Original ledgers unchanged; any new ledgers preserved for inspection.' >&2
  fi
}
trap restore_on_failure EXIT
# Stop only the two paper engines for the consistent migration. Coin and BTC
# collectors continue; there are no actual exchange orders to cancel.
systemctl stop cbot-paper cbot-fee-filter-paper
(cd "$task_release"; "$task_release/venv/bin/python" -m coinbase_bot.product_wallets migrate --strategy baseline --source /var/lib/cbot/observed-v1.sqlite --state /var/lib/cbot/products/baseline)
(cd "$task_release"; "$task_release/venv/bin/python" -m coinbase_bot.product_wallets migrate --strategy fee-filter --source /var/lib/cbot/fee-filter-v1.sqlite --state /var/lib/cbot/products/fee-filter)
python3 - "$task_release" <<'PY'
from pathlib import Path
import os,pwd,sys
identity=pwd.getpwnam('cbot');root=Path('/var/lib/cbot/products')
for path in [root,*root.rglob('*')]:
    os.chown(path,identity.pw_uid,identity.pw_gid)
    path.chmod(0o700 if path.is_dir() else 0o600)
release=sys.argv[1];updates={}
for name in ('cbot-paper','cbot-fee-filter-paper','cbot-status','cbot-dashboard','shaneathon-health','shaneathon-backup'):
    path=Path('/etc/systemd/system')/(name+'.service');text=path.read_text()
    old=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    if not old.startswith(('/opt/cbot/releases/','/opt/pbot/releases/','/opt/shaneathon-ops/releases/')): raise SystemExit('Unexpected unit path')
    text=text.replace(old,release)
    if name in ('cbot-paper','cbot-fee-filter-paper'):
        strategy='baseline' if name=='cbot-paper' else 'fee-filter'
        status='product-baseline.sqlite' if strategy=='baseline' else 'product-fee-filter.sqlite'
        stop='STOP' if strategy=='baseline' else 'STOP-FEE-FILTER'
        command='ExecStart='+release+'/venv/bin/python -m coinbase_bot.product_wallets watch --strategy '+strategy+' --state /var/lib/cbot/products/'+strategy+' --status /var/lib/cbot/'+status+' --kill-file /var/lib/cbot/'+stop
        text='\n'.join(command if line.startswith('ExecStart=') else line for line in text.splitlines())+'\n'
    if name=='cbot-status': text=text.replace('--ledger /var/lib/cbot/observed-v1.sqlite','--ledger /var/lib/cbot/product-baseline.sqlite')
    updates[path]=text
for path,text in updates.items(): path.write_text(text)
PY
systemctl daemon-reload
systemctl start cbot-paper cbot-fee-filter-paper
systemctl restart cbot-status cbot-dashboard
python3 - <<'PY'
import json,sqlite3,time
for attempt in range(30):
    try:
        for name in ('baseline','fee-filter'):
            with sqlite3.connect('file:/var/lib/cbot/product-'+name+'.sqlite?mode=ro',uri=True) as db:
                row=db.execute('SELECT observed_at,payload FROM bot_snapshot WHERE id=1').fetchone()
            report=json.loads(row[1])
            assert 0<=time.time()-row[0]<20 and report['operation_mode']=='PRODUCT_WALLETS_PAPER'
            assert report['account']['live_orders_enabled'] is False
            assert set(report['product_wallets'])=={'BTC-USD','ETH-USD','XRP-USD','SOL-USD'}
        break
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,AssertionError):
        if attempt==29: raise SystemExit('Independent wallet readiness not established')
        time.sleep(1)
PY
install -m 640 -o root -g cbot /dev/null /var/lib/cbot/PRODUCT-WALLETS-ACTIVE
task_committed=1
systemctl start --no-block shaneathon-health.service || true
python3 - <<'PY'
import json,sqlite3
for strategy in ('baseline','fee-filter'):
    with sqlite3.connect('file:/var/lib/cbot/product-'+strategy+'.sqlite?mode=ro',uri=True) as db:
        report=json.loads(db.execute('SELECT payload FROM bot_snapshot WHERE id=1').fetchone()[0])
    print(strategy.upper())
    for product,data in report['product_wallets'].items():
        a=data['account']
        print(product,'| allocation:',data['wallet_initial_allocation'],'| cash:',a['cash'],'| P/L:',a['realized_pnl'],'| open cost:',a['open_exposure'])
PY
echo 'Independent wallets active at https://cbot.shaneathon.com . Select Crypto to switch all balances/P&L/charts together.'
echo 'Each original $1,000 allocation is split $250 per coin; historical P/L and holdings are carried forward, not reset.'
echo 'Exposure and daily loss budgets are also split four ways; coins cannot borrow from each other.'
echo 'Unsubmitted BUY proposals were cancelled without fees during migration; holdings/exits and original archive ledgers preserved.'
echo 'Coinbase collectors and PBot were not restarted. Real trading remains disabled.'
