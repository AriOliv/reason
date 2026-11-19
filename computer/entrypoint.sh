#!/bin/sh
# The VNC password comes from the environment (never baked into the image).
set -eu
[ -n "${COMPUTER_VNC_PASSWORD:-}" ] || { echo "computer: COMPUTER_VNC_PASSWORD is required" >&2; exit 1; }
x11vnc -storepasswd "$COMPUTER_VNC_PASSWORD" /tmp/vncpass >/dev/null 2>&1
chmod 600 /tmp/vncpass
mkdir -p /data/profile /data/output
exec supervisord -c /etc/supervisor/reason.conf
