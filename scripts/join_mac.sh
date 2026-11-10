#!/usr/bin/env bash
set -euo pipefail

WORKERS="${1:-4}"
LAN_URL="http://192.168.1.5:8085"
TUNNEL_URL="https://seniors-auditor-presentation-george.trycloudflare.com"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if curl -sf --max-time 2 "$LAN_URL/api/telemetry" >/dev/null 2>&1; then
  COORD_URL="$LAN_URL"
else
  COORD_URL="$TUNNEL_URL"
fi

NODE_ID="macbook-$(hostname -s 2>/dev/null || echo worker)"
echo "[MacAgent] Connecting remote-controlled agent '$NODE_ID' ($WORKERS threads) -> $COORD_URL"

if [ "${AUTOSTART:-1}" = "1" ] && [ "$(uname -s)" = "Darwin" ]; then
  python3 -u "$REPO_ROOT/scripts/mac_agent.py" \
    --node-id "$NODE_ID" \
    --workers "$WORKERS" \
    --coordinator-url "$COORD_URL" \
    --install-autostart
  echo "[MacAgent] Background LaunchAgent installed! Windows coordinator now has full remote control."
else
  exec python3 -u "$REPO_ROOT/scripts/mac_agent.py" \
    --node-id "$NODE_ID" \
    --workers "$WORKERS" \
    --coordinator-url "$COORD_URL"
fi
