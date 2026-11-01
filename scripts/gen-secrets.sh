#!/usr/bin/env bash
# Generate strong secrets.
#   ./scripts/gen-secrets.sh            print them
#   ./scripts/gen-secrets.sh .env       write them into .env (replacing existing values)
set -euo pipefail
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1" || true; }
# JWT: 48 chars -> HS384 in core (jjwt picks by key length); agent-service accepts HS256/384/512.
declare -A SECRETS=(
  [POSTGRES_PASSWORD]="$(rand 32)"
  [JWT_SECRET]="$(rand 48)"
  [INTERNAL_API_KEY]="$(rand 40)"
  [OPERATOR_KEY]="$(rand 32)"
)
target="${1:-}"
for key in POSTGRES_PASSWORD JWT_SECRET INTERNAL_API_KEY OPERATOR_KEY; do
  line="${key}=${SECRETS[$key]}"
  if [ -z "$target" ]; then
    echo "$line"
  elif grep -q "^${key}=" "$target"; then
    sed -i "s|^${key}=.*|${line}|" "$target"
  else
    echo "$line" >> "$target"
  fi
done
[ -n "$target" ] && echo "Wrote POSTGRES_PASSWORD, JWT_SECRET, INTERNAL_API_KEY, OPERATOR_KEY to $target" >&2 || true
