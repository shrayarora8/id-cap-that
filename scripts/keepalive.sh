#!/usr/bin/env bash
# Stop Render's free tier falling asleep.
#
# It spins the service down after ~15 minutes with no traffic, and the next
# visitor gets a 502 for 30-60 seconds while it wakes. A judge who scans the
# QR code and sees that will assume it is broken, not asleep.
#
# So: ping /health every 10 minutes. That is cheap, hits nothing paid, and
# keeps the service warm for anyone who arrives cold.
#
#   ./scripts/keepalive.sh &
#
set -u
URL="${1:-https://id-cap-that.onrender.com}"
EVERY="${2:-600}"

echo "keeping $URL awake, every ${EVERY}s. ctrl-c to stop."
while true; do
  CODE=$(curl -s -o /dev/null -m 45 -w '%{http_code}' "$URL/health" || echo 000)
  printf '%s  %s\n' "$(date +%H:%M:%S)" "$CODE"
  sleep "$EVERY"
done
