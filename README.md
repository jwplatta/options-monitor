# Options Monitor

Options-data and market-monitoring dashboard built with Streamlit. Displays GEX, flow tape, open interest, volatility skew, and fixed-strike vol surfaces for SPX/SPXW options.

## Stack

- `uv` for environment and dependency management
- `streamlit` for the dashboard UI
- `ruff` for linting and formatting
- `mypy` for strict type checking
- `pytest` with coverage reporting
- `src/` layout for clean packaging

## Data Sources

Tractatus `DataReader` reads intraday option snapshots and `ibkr-paper` candles from MinIO. Historical options come from the `tickrake-historical` MinIO bucket, with the Tractatus Iceberg fallback when configured. The reader caches Parquet files under `~/.tractatus/cache` for DuckDB historical queries.

## Configuration

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `MINIO_ENDPOINT` | `http://localhost:9000` | MinIO API endpoint |
| `MINIO_INTRADAY_BUCKET` | `tickrake-intraday` | Intraday snapshots and candles |
| `MINIO_HISTORICAL_BUCKET` | `tickrake-historical` | Historical Parquet files |
| `MINIO_ACCESS_KEY` | — | MinIO access key |
| `MINIO_SECRET_KEY` | — | MinIO secret key |
| `TRACTATUS_CACHE_DIR` | `~/.tractatus/cache` | Local Parquet cache |
| `OPTIONS_MONITOR_CACHE_DIR` | `~/.cache/options-monitor` | Persistent Vol Regime SQLite observations; mounted separately from Tractatus in Docker |
| `PORT` | `8501` | Docker host port |

## Quick Start

```bash
# Dev (local uv)
bin/run_dev.sh

# Docker
bin/run_docker.sh

# Development container with live source reload, reading the running production MinIO
make dev-shared
```

`make dev-shared` runs an isolated development container at <http://localhost:8502> and connects to the existing MinIO endpoint (default `http://host.docker.internal:9000`). It does not start, stop, or modify MinIO. Stop only this development container with `make dev-shared-stop`.

Vol Regime stores historical ATM IV and risk-reversal observations in
`$OPTIONS_MONITOR_CACHE_DIR/vol_regime.sqlite3`. SQLite is embedded in the app;
there is no separate database container. The first chart load fills missing
observations from historical Parquet. Later loads reuse them across app restarts.
Rows do not expire by age; a changed source file or calculation version causes
recomputation. The chart checks the latest published intraday chain on each
30-second refresh.

The Volatility Skew chart uses the same lookback choices as Vol Regime. It plots
the latest 30-DTE OTM put/call IV curve against the historical daily closing
skews nearest 30 DTE. Historical strikes are aligned by distance from each
day's spot, then shown on the current strike scale. The historical 10th–90th
percentile band and median use curves stored in
`$OPTIONS_MONITOR_CACHE_DIR/vol_skew.sqlite3`; source changes invalidate a day.

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

### Vol query benchmarks

Run these from the host with the MinIO credentials in `.env`. Use `--endpoint
http://localhost:9000` when `.env` is configured for Docker's
`host.docker.internal` address:

```bash
uv run --env-file .env python scripts/benchmark_vol_regime.py --endpoint http://localhost:9000 --lookback-days 360
uv run --env-file .env python scripts/benchmark_fixed_strike_vol.py --endpoint http://localhost:9000 --lookback-days 30
```

Both scripts default to QQQ, SPY, IWM, GLD, and CRWV. They time date discovery,
Parquet downloads, queries, and calculations separately. `--as-of latest`
(the default) anchors each ticker to its newest archived date; `--as-of today`
uses the dashboard's current window. Use `--cache-dir /tmp/vol-bench-cache` to
measure an uncached download without changing the dashboard's cache. The 360-day
run can download several gigabytes to a fresh cache. Stage timings are
inclusive, so nested stages overlap.

## Structure

```text
src/options_monitor/
├── app.py              # Streamlit entrypoint and tab routing
├── data/               # shared Tractatus reader and cached dashboard loaders
├── calc/               # pure computation — GEX, flow, vol, OI, spreads
├── charts/             # Plotly figure builders
└── tabs/               # Streamlit tab renderers (gex, flow, oi, vol/*, history)
```
