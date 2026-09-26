#!/usr/bin/env bash
# Expose the local server over HTTPS so a phone can reach it.
#
# A phone will not grant microphone access to a plain-http page, and a laptop
# IP on the same wifi is still plain http, so there is no way round this. A
# Cloudflare quick tunnel needs no account and dies when you close it, which
# also means the demo URL is not left running unattended.
#
#   ./scripts/tunnel.sh
#
# Then open the printed https URL on your phone.
set -euo pipefail
PORT="${1:-8000}"

if ! curl -sf -m 2 "http://127.0.0.1:${PORT}/health" > /dev/null; then
  echo "Nothing is listening on ${PORT}. Start the server first:"
  echo "  .venv/bin/uvicorn server.main:app --reload --port ${PORT}"
  exit 1
fi

echo "Server is up. Opening a tunnel to it..."
echo "Look for the https://<something>.trycloudflare.com line below."
echo
exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"
