#!/usr/bin/env bash
# Local / bare-metal run. Docker is nicer - this is for a quick spin.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-python3}
PORT=${PORT:-8000}
WORKERS=${WEB_CONCURRENCY:-1}

if [ ! -d .venv ]; then
  $PY -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
fi

export OUTBOUND_CONCURRENCY=${OUTBOUND_CONCURRENCY:-64}
export SHEET_CONCURRENCY=${SHEET_CONCURRENCY:-200}
export ALLOWED_HOSTS=${ALLOWED_HOSTS:-cbexams.com}

echo "ssc marks analyser -> http://127.0.0.1:${PORT}"
exec ./.venv/bin/uvicorn app.api:app --host 0.0.0.0 --port "$PORT" \
     --workers "$WORKERS" --log-level warning
