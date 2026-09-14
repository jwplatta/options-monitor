#!/usr/bin/env bash
set -euo pipefail

# Load .env if present (values act as defaults; existing env vars take precedence)
if [[ -f "$(dirname "$0")/../.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$(dirname "$0")/../.env"
  set +a
fi

export TICKRAKE_HOME="${TICKRAKE_HOME:-$HOME/.tickrake}"
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
export MINIO_BUCKET="${MINIO_BUCKET:-tickrake-intraday}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"

exec uv run streamlit run src/options_monitor/app.py --server.port=8503
