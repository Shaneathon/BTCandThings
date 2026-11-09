#!/usr/bin/env bash
# Remove retired Coinbase endpoints/portal cards, not historical databases.
set -euo pipefail
umask 022
[[ "${1:-}" == --apply && "$EUID" == 0 ]] || { echo 'Use --apply as root'; exit 2; }
task_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /var/lib/shaneathon-ops/BTC15-ONLY ]]
grep -Fq 'SHANEATHON_BTC15_ONLY=1' /etc/systemd/system/pbot-dashboard.service.d/btc15-scope.conf
grep -Fq 'SHANEATHON_BTC15_ONLY=1' /etc/systemd/system/btc-multiasset-research.service.d/btc15-scope.conf
bash "$task_source/deploy/refresh-pbot-display.sh" --apply
task_backup="$(mktemp -d /opt/pbot/coinbase-retirement.XXXXXX)"
chmod 700 "$task_backup"
cp /etc/shaneathon-portal-links.json "$task_backup/links.json"
cp /var/www/shaneathon-portal/index.html "$task_backup/index.html"
for host in coin cbot; do
  [[ -f "/etc/nginx/sites-available/$host.shaneathon.com" ]]
  [[ -f "/etc/letsencrypt/live/$host.shaneathon.com/fullchain.pem" ]]
  cp "/etc/nginx/sites-available/$host.shaneathon.com" "$task_backup/$host.nginx"
done
task_done=0
restore_endpoints() {
  if [[ "$task_done" == 0 ]]; then
    cp "$task_backup/links.json" /etc/shaneathon-portal-links.json
    cp "$task_backup/index.html" /var/www/shaneathon-portal/index.html
    for host in coin cbot; do cp "$task_backup/$host.nginx" "/etc/nginx/sites-available/$host.shaneathon.com"; done
    nginx -t && systemctl reload nginx
    echo 'Previous portal and web configurations restored; no financial data changed.' >&2
  fi
}
trap restore_endpoints EXIT
python3 - "$task_source" <<'PY'
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(sys.argv[1])/'portal'))
from build import render
path=Path('/etc/shaneathon-portal-links.json')
links=[item for item in json.loads(path.read_text()) if item['url'].rstrip('/') not in ('https://coin.shaneathon.com','https://cbot.shaneathon.com')]
html=render(links)
path.write_text(json.dumps(links,indent=2)+'\n')
Path('/var/www/shaneathon-portal/index.html').write_text(html)
for host in ('coin','cbot'):
    domain=host+'.shaneathon.com'
    Path('/etc/nginx/sites-available/'+domain).write_text(f'''server {{
    listen 80;
    server_name {domain};
    return 410;
}}
server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    return 410;
}}
''')
PY
nginx -t
systemctl reload nginx
for name in coin-collector coin-status coin-dashboard coinbase-recorder cbot-paper cbot-status cbot-dashboard cbot-fee-filter-paper; do
  if systemctl cat "$name.service" >/dev/null 2>&1; then
    systemctl disable --now "$name.service"
    if systemctl is-active --quiet "$name.service"; then echo "$name unexpectedly active" >&2; exit 1; fi
  fi
done
for host in coin cbot; do
  task_code="$(curl --resolve "$host.shaneathon.com:443:127.0.0.1" -sS -o /dev/null -w '%{http_code}' "https://$host.shaneathon.com/")"
  [[ "$task_code" == 410 ]]
done
task_done=1
echo 'PBot display: Champion, Challenger B, BTC 15m Research only. Other wallets archived, never deleted.'
echo 'Coinbase bot/tracker removed from portal; public endpoints retired (HTTP 410); Coinbase data collection stopped.'
echo 'BTC15-only collection scope retained. PBot engine, balances, history and $1.50 cap unchanged; real trading disabled.'
echo "Web configuration backups: $task_backup"
