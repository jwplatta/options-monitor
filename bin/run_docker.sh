#!/usr/bin/env bash
set -euo pipefail

# Load .env if present (values act as defaults; existing env vars take precedence)
if [[ -f "$(dirname "$0")/../.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$(dirname "$0")/../.env"
  set +a
fi

export MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
export MINIO_INTRADAY_BUCKET="${MINIO_INTRADAY_BUCKET:-tickrake-intraday}"
export MINIO_HISTORICAL_BUCKET="${MINIO_HISTORICAL_BUCKET:-tickrake-historical}"
export TRACTATUS_CACHE_DIR="${TRACTATUS_CACHE_DIR:-$HOME/.tractatus/cache}"
export OPTIONS_MONITOR_CACHE_DIR="${OPTIONS_MONITOR_CACHE_DIR:-$HOME/.cache/options-monitor}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"

exec docker compose up --build
