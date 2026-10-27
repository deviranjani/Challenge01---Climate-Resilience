#!/usr/bin/env bash
# Start the Heat Planner UI on http://127.0.0.1:8080 (override with PORT=...).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] && set -a && . ./.env && set +a
exec .venv/bin/uvicorn heat_planner.api:app --host 127.0.0.1 --port "${PORT:-8080}" "$@"
