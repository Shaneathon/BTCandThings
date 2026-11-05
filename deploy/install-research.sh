#!/usr/bin/env bash
# Separate shadow service. Never touches btc-collector or btc-challenger.
set -euo pipefail
umask 022
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
install_root="${BTC_RESEARCH_INSTALL_ROOT:-/opt/btcandthings-research}"
state_root="${BTC_RESEARCH_STATE_ROOT:-/var/lib/btcandthings-research}"
mode="${1:---prepare}"
if [[ "$mode" != --prepare && "$mode" != --start && "$mode" != --start-cloud ]]; then
  echo 'Usage: bash deploy/install-research.sh [--prepare|--start|--start-cloud]' >&2; exit 2
fi
if [[ "$mode" != --prepare && ( "$install_root" != /opt/btcandthings-research || "$state_root" != /var/lib/btcandthings-research ) ]]; then
  echo '--start uses the standard /opt and /var/lib paths; overrides are preparation-only.' >&2; exit 2
fi
if [[ "$mode" != --prepare && "$EUID" -ne 0 ]]; then
  echo '--start requires root to register the separate systemd service.' >&2; exit 2
fi
if [[ "$install_root" != /* || "$state_root" != /* || "$install_root" == *' '* || "$state_root" == *' '* ]]; then
  echo 'Installation and state paths must be absolute with no spaces.' >&2; exit 2
fi
# Immutable releases avoid changing code underneath an existing process.
release_id="$(date -u +%Y%m%dT%H%M%S)-$$"
release_root="$install_root/releases/$release_id"
mkdir -p "$release_root/collection" "$state_root" "$release_root/BTCandThings_Website/BTCandThings_Upload"
# Copy only reviewed source; never clone .env, secrets, databases or local history.
for file in "$source_root"/collection/*.py; do
  install -m 644 "$file" "$release_root/collection/"
done
for name in market_workspace.py market_board.py market_candles.py tracker_panels.py market_history.py; do
  install -m 644 "$source_root/BTCandThings_Website/BTCandThings_Upload/$name" "$release_root/BTCandThings_Website/BTCandThings_Upload/$name"
done
python3 "$release_root/collection/preflight.py" "$release_root"
python3 -m venv "$release_root/venv"
"$release_root/venv/bin/python" -m pip install --disable-pip-version-check 'pandas>=2.1,<3'
"$release_root/venv/bin/python" -m unittest discover -s "$release_root/collection" -v
if [[ "$mode" == --prepare ]]; then
  echo "PREPARED: $release_root"
  echo 'No systemd services were installed, stopped or started.'
  exit 0
fi
if systemctl is-active --quiet btc-multiasset-research.service; then
  echo 'Existing multiasset service is active; refusing to replace it automatically.' >&2; exit 1
fi
if [[ -e /etc/systemd/system/btc-multiasset-research.service ]]; then
  echo 'An existing unit requires review; refusing to overwrite it.' >&2; exit 1
fi
# A failed live preflight leaves all production services unchanged.
(umask 077; "$release_root/venv/bin/python" "$release_root/collection/ten_streams.py" --db "$state_root/preflight.sqlite")
if [[ "$mode" == --start-cloud ]]; then
  "$release_root/venv/bin/python" "$release_root/collection/configure_cloud.py"
fi
cat > /etc/systemd/system/btc-multiasset-research.service <<EOF
[Unit]
Description=BTCandThings ten-stream local shadow research collector
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
DynamicUser=yes
StateDirectory=btcandthings-research
WorkingDirectory=$release_root
EnvironmentFile=-/etc/btcandthings-research.env
ExecStart=$release_root/venv/bin/python $release_root/collection/ten_streams.py --db /var/lib/btcandthings-research/research.sqlite --loop
Restart=on-failure
RestartSec=30
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now btc-multiasset-research.service
echo 'Started only btc-multiasset-research.service; existing collectors were untouched.'
validation_flags=''
if [[ "$mode" == --start-cloud ]]; then validation_flags=' --require-cloud'; fi
echo "Validate after its first pass: $release_root/venv/bin/python $release_root/collection/ten_streams.py --db /var/lib/btcandthings-research/research.sqlite --validate$validation_flags"
