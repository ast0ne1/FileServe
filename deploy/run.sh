#!/bin/bash
set -euo pipefail

cd /opt/fileserve

if [[ -f /opt/fileserve/.env ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' /opt/fileserve/.env)
  set +a
fi

exec /opt/fileserve/.venv/bin/gunicorn -b "${HOST:-0.0.0.0}:${PORT:-8081}" app.main:app
