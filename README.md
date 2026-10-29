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
| `OPTIONS_MONITOR_CACHE_DIR` | `~/.cache/options-monitor` | Shared SQLite cache database; mounted separately from Tractatus in Docker |
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

Fixed Strike, Vol Regime, and Volatility Skew share the embedded SQLite database
`$OPTIONS_MONITOR_CACHE_DIR/options_monitor_cache.sqlite3`; there is no separate
database container. The database and all cache tables are created on first use.
Current table definitions are managed centrally in the app. Incompatible caches
are discarded and rebuilt without migrations. Historical
cache rows are source-validated and reused across app restarts. Vol Regime retires
rows using its configurable retention period. A changed source file or calculation version triggers recomputation where
applicable. Vol Regime still checks the latest published intraday chain on each
30-second refresh.

The Volatility Skew chart uses the same lookback choices as Vol Regime. It plots
the latest 30-DTE OTM put/call IV curve against the historical daily closing
skews nearest 30 DTE. Historical strikes are aligned by distance from each
day's spot, then shown on the current strike scale. The historical 10th–90th
percentile band and median use curves stored in the shared SQLite cache; source
changes invalidate a day.

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

## Historical chart caches

Vol Regime stores calculated daily ATM IV and risk reversal in the shared Options
Monitor SQLite cache. A single in-process worker refreshes historical data through
Tractatus CacheReader, while chart requests reuse prior successful observations.
Symbols selected on demand are cached without joining the warmup list.

The sidebar **Settings** page saves one shared warmup list for all chart jobs,
initially empty. Its Vol Regime section saves target DTE and retention separately
in SQLite. Retention defaults to 365 calendar days. Daily cleanup
also runs after app downtime, and queries never rehydrate dates outside retention.
Status and last successful verification are shown above the chart; old archive
coverage is reported independently from refresh status.

All current cache schemas are centralized in `data/sqlite_cache.py`. Job
registration defines validation, computation, cleanup, refresh frequency and
warmup defaults. Vol Skew and Fixed Strike retain their existing caches until
separate chart updates. See [the implementation plan](docs/plans/vol-regime-cache-jobs.md)
for the schema and measurements.

Dev defaults to `~/.cache/options-monitor-dev`, production keeps its existing cache
path, and `OPTIONS_MONITOR_CACHE_DIR` overrides either. Incompatible SQLite caches are automatically rebuilt from current definitions,
including saved settings. There are no schema versions or migration history.

`OPTIONS_MONITOR_TIMEZONE` sets the timezone used for cache job calendar dates and
daily retention cleanup. It defaults to `America/Chicago` (Central Time, including
daylight saving changes). Set it to another IANA timezone to override it. Persisted
job timestamps remain UTC; historical chain sampling remains at 10:30 New York time.

Vol Regime and the shared job framework do not track calculation versions. When
changing metric formulas or snapshot selection without changing the schema, stop
the app and discard its cache database (including SQLite WAL/SHM files) before
restarting to recompute results. Source-object revision changes still trigger
automatic refreshes. Skew and Fixed Strike retain their existing implementation
until their separate cache updates.

After changing cache schemas or worker code during development, restart the dev
container: Streamlit hot reload can leave existing background threads executing
older code. Option-root dropdowns are seeded locally from committed YAML;
no bucket discovery or root-refresh job runs.

### Option root registry

Supported roots are defined in [`src/options_monitor/config/option_roots.yaml`](src/options_monitor/config/option_roots.yaml):

```yaml
option_roots:
  - option_root: SPXW
    underlying: $SPX
    asset_class: index
  - option_root: QQQ
    underlying: QQQ
    asset_class: etf
```

Edit and commit this file, then restart the app to add or change supported roots.
The packaged YAML is validated and seeds the indexed `option_roots` table whenever
SQLite is created or rebuilt. Restarting also syncs config edits into an existing
database: existing rows are upserted, removed YAML roots leave the registry, and
unchanged rows retain their timestamp. There are no MinIO root scans or refresh
buttons. The **Settings** page points to the configuration file.

`option_root` and `underlying` are required, nonempty strings; duplicate roots are
rejected. Additional JSON-compatible YAML fields are retained in each row's
`metadata_json`. Each row also stores `namespace_id`, `refreshed_at` (configuration
sync time), and nullable `last_error`. The initial 90 entries were copied from
Tickrake's configured stock/ETF universes plus SPXW mapped to `$SPX`; the app does
not read Tickrake's configuration at runtime.

The supported-root registry is separate from the shared warmup list. Configuring
a root makes it selectable; only roots selected in the warmup list run recurring
historical jobs. A reset clears user settings but repopulates configured roots.
