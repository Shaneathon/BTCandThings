#!/usr/bin/env bash
set -euo pipefail
for name in btc-collector.service btc-challenger.service btc-multiasset-research.service; do
  printf '%s: ' "$name"
  systemctl is-active "$name" || true
done
release_root="$(systemctl show btc-multiasset-research.service --no-pager -p WorkingDirectory --value)"
if [[ "$release_root" != /opt/btcandthings-research/releases/* || ! -x "$release_root/venv/bin/python" ]]; then
  echo 'Research collector is not installed at the expected location.' >&2; exit 1
fi
"$release_root/venv/bin/python" "$release_root/collection/ten_streams.py" \
  --db /var/lib/btcandthings-research/research.sqlite --validate "$@"
