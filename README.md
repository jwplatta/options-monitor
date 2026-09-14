# Options Monitor

Options-data and market-monitoring dashboard built with Streamlit.

## Stack

- `uv` for environment and dependency management
- `streamlit` for the dashboard UI
- `ruff` for linting and formatting
- `mypy` for strict type checking
- `pytest` with coverage reporting
- `src/` layout for clean packaging

## Data Sources

| Data | Source |
|---|---|
| Intraday option chains (latest snapshot) | MinIO via S3 API — `intraday/schwab/{ROOT}.json` index + per-expiry CSVs |
| Intraday time-series (Flow/History) | Local timestamped CSVs written by tickrake jobs (`~/.tickrake/data/options/schwab/`) |
| Historical option chains | Local parquet cache (`~/.tickrake/…`); downloaded from S3 on cache miss |
| Historical index | Local `ROOT.json` written by the tickrake reconciler at 16:00 weekdays |

All tickrake I/O is wrapped in `src/options_monitor/tickrake/` — a clean extraction boundary designed for eventual packaging as a standalone `TickrakeClient`.

## Configuration

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `TICKRAKE_HOME` | `~/.tickrake` | Root of the local tickrake data directory |
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO endpoint for intraday data |
| `MINIO_BUCKET` | `tickrake-intraday` | MinIO bucket |
| `MINIO_ACCESS_KEY` | — | MinIO access key |
| `MINIO_SECRET_KEY` | — | MinIO secret key |
| `S3_BUCKET` | — | AWS S3 bucket for historical archive |
| `S3_REGION` | `us-east-1` | AWS region |
| `PORT` | `8503` | Docker host port |

AWS credentials for S3 are resolved via the standard credential chain (`~/.aws/credentials`, IAM role, etc.) — no explicit key variables needed.

## Quick Start

```bash
# Dev (local uv)
bin/run_dev.sh

# Docker
bin/run_docker.sh
```

Or manually:

```bash
uv sync
uv run streamlit run src/options_monitor/app.py
```

## Development

```bash
uv run ruff check .
uv run ruff format .
uv run mypy
uv run pytest
```

## Structure

```text
.
├── bin/
│   ├── run_dev.sh          # start dev server (sources .env)
│   └── run_docker.sh       # build and run Docker container
├── docs/
├── src/options_monitor/
│   ├── tickrake/           # MinIO + S3 + filesystem data access
│   │   ├── client.py       # TickrakeClient facade
│   │   ├── intraday.py     # MinIO intraday index + CSV fetching
│   │   ├── archive.py      # S3 historical parquet + local cache
│   │   ├── filesystem.py   # local timestamped CSV scanning
│   │   └── config.py       # connection config from env vars
│   ├── data/
│   ├── tabs/
│   └── app.py
└── tests/
```
