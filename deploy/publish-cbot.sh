#!/usr/bin/env bash
# Add only CBot's hostname after its paper services are installed and healthy.
set -euo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run as root on the droplet'; exit 2; }
for name in cbot-paper cbot-status cbot-dashboard; do systemctl is-active --quiet "$name.service"; done
curl -fsS --retry 5 --retry-connrefused --retry-delay 2 --max-time 10 http://127.0.0.1:8503/_stcore/health
printf '\n'
command -v certbot >/dev/null
nginx -t
python3 - <<'PY'
import socket
from urllib.request import urlopen
with urlopen('http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address',timeout=5) as response:
    expected=response.read(100).decode().strip()
try:
    answers=socket.getaddrinfo('cbot.shaneathon.com',443,type=socket.SOCK_STREAM)
except socket.gaierror:
    raise SystemExit('CBot services are installed. DNS is not ready; save its A record, then rerun only publish-cbot.sh.')
addresses={row[4][0] for row in answers}
if addresses!={expected}:
    raise SystemExit('CBot services are installed. DNS does not exclusively point to this droplet; check A/AAAA records before publication.')
print('CBot DNS points to this droplet.')
PY
for path in /etc/nginx/sites-available/cbot.shaneathon.com /etc/nginx/sites-enabled/cbot.shaneathon.com; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing $path; refusing replacement. Inspect before retrying publication."; exit 1; }
done
if grep -Rq 'cbot\.shaneathon\.com' /etc/nginx/sites-enabled /etc/nginx/conf.d; then
  echo 'CBot hostname already appears in active configuration; refusing duplicate route'; exit 1
fi
set -o noclobber
cat > /etc/nginx/sites-available/cbot.shaneathon.com <<'NGINX'
server {
    listen 80;
    server_name cbot.shaneathon.com;
    location / {
        proxy_pass http://127.0.0.1:8503;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_buffering off;
    }
}
NGINX
ln -s /etc/nginx/sites-available/cbot.shaneathon.com /etc/nginx/sites-enabled/cbot.shaneathon.com
if nginx -t; then
  systemctl reload nginx
else
  rm /etc/nginx/sites-enabled/cbot.shaneathon.com
  echo 'CBot route failed validation and was disabled. Existing active Nginx configuration was not reloaded.' >&2
  exit 1
fi
certbot --non-interactive --nginx -d cbot.shaneathon.com --redirect
curl -fsS --retry 5 --retry-delay 2 --max-time 15 https://cbot.shaneathon.com/_stcore/health
printf '\nCBot HTTPS health check passed: https://cbot.shaneathon.com\n'
