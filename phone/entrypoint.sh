#!/bin/sh
# reason phone: keep adb connected to the Android device and serve mobile-mcp over HTTP.
# The MCP requires a Bearer token and listens only on the agent's internal network.
set -eu
[ -n "${MOBILEMCP_AUTH:-}" ] || { echo "phone: MOBILEMCP_AUTH is required" >&2; exit 1; }
DEVICE="${PHONE_ADB_TARGET:-android:5555}"
adb start-server >/dev/null 2>&1
(
  while true; do
    adb devices | grep -q "^${DEVICE}[[:space:]]*device" || adb connect "$DEVICE" >/dev/null 2>&1 || true
    sleep 10
  done
) &
exec node /opt/phone/node_modules/@mobilenext/mobile-mcp/lib/index.js --listen "${PHONE_LISTEN:-0.0.0.0:3000}"
