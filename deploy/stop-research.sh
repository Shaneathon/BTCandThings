#!/usr/bin/env bash
# Stops ONLY the optional research service; preserves state and credentials.
set -euo pipefail
systemctl disable --now btc-multiasset-research.service
printf '%s\n' 'Research service stopped. Existing Champion/Challenger were not changed; collected files remain in /var/lib/btcandthings-research.'
