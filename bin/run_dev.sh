#!/usr/bin/env bash
set -euo pipefail

export OPTIONS_MONITOR_MINIO_ENDPOINT="${OPTIONS_MONITOR_MINIO_ENDPOINT:-http://localhost:9000}"
export OPTIONS_MONITOR_MINIO_BUCKET="${OPTIONS_MONITOR_MINIO_BUCKET:-tickrake-intraday}"
export OPTIONS_MONITOR_MINIO_ACCESS_KEY="${OPTIONS_MONITOR_MINIO_ACCESS_KEY:-minioadmin}"
export OPTIONS_MONITOR_MINIO_SECRET_KEY="${OPTIONS_MONITOR_MINIO_SECRET_KEY:-minioadmin}"

exec uv run streamlit run src/options_monitor/app.py
