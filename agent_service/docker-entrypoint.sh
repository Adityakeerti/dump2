#!/bin/sh
# Agent service entrypoint: migrate -> seed personas + verified corpus (idempotent) -> serve.
set -e

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "[entrypoint] waiting for database + applying migrations"
  i=0
  until alembic upgrade head; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then echo "[entrypoint] database not reachable, giving up"; exit 1; fi
    sleep 2
  done
fi

if [ "${SKIP_SEED:-0}" != "1" ]; then
  echo "[entrypoint] seeding personas and verified corpus (idempotent)"
  python -m scripts.seed || echo "[entrypoint] WARNING: seed failed; chat will fall back to the offline engine"
fi

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*' --log-config logging.ini
