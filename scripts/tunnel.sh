#!/usr/bin/env bash
# Public HTTPS address for the phone app: ngrok static domain -> Caddy (localhost:80).
# Caddy blocks operator routes (dashboard, emergency, resolve/escalate, notice publishing) on that name.
# Needs: ngrok installed, `ngrok config add-authtoken ...` done once, NGROK_DOMAIN in Project/.env
set -euo pipefail
cd "$(dirname "$0")/.."
domain="${NGROK_DOMAIN:-$(grep -s '^NGROK_DOMAIN=' .env | cut -d= -f2-)}"
if [ -z "$domain" ]; then
  echo "Set NGROK_DOMAIN=<your-name>.ngrok-free.app in Project/.env" >&2
  exit 1
fi
exec ngrok http 80 --url="https://${domain}" --log=stdout --log-level=warn
