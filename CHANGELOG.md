# Changelog

## Unreleased

### Changed
- Removed manual calculation-version tracking from Vol Regime and shared cache jobs; formula changes require discarding the disposable cache. Remote source revision validation remains.
- Replaced SQLite schema versions and migration history with current definitions; incompatible disposable caches are rebuilt automatically, including saved settings.
- Cache Settings now has a shared warmup-list section for all chart jobs, initially empty; SPXW is no longer automatically warmed. Chart parameters remain separate.
- Moved per-root Vol Regime cache status, verification time, and refresh errors into its Data Table, including selected roots whose chart points are not ready.
- Moved Vol Regime warmup and retention controls to a dedicated Cache Settings page in the sidebar navigation.
- Cache job calendar dates and daily cleanup use configurable `OPTIONS_MONITOR_TIMEZONE`, defaulting to `America/Chicago` (Central Time).
- Vol Regime now reads persistent historical IV/RR metrics while a bounded background worker refreshes revisioned CacheReader sources. Warmup lists and configurable 365-day retention persist in the shared SQLite database; daily cleanup retires expired metrics.
- Historical cache migrations destructively rebuild legacy Vol Regime tables. Root metadata survives app restarts and refreshes on the shared worker.
- Moved symbol selection from the sidebar into independent chart controls; Vol Regime retains its multi-symbol selector.
- Simplified Vol subtabs to Fixed Strike Vol, Volatility Skew, and Vol Regime. Added a latest 30-DTE skew chart against a persistent historical 10th–90th percentile band.
- Vol Regime now refreshes its current chain every 30 seconds and stores source-validated historical IV and risk-reversal observations in a separate persistent Options Monitor SQLite cache.
- Read only the Parquet columns needed for Vol Regime IV and risk reversal, reducing warm-cache load time.
- Load only the selected Vol subtab and defer Vol Regime historical caching until a current chain is usable.
- Switched intraday options, historical Parquet, and ibkr-paper candles to Tractatus DataReader with a shared DuckDB connection and local reader cache.
- Migrated `options_monitor.tickrake` to `tractatus.tickrake` — removed local tickrake module, now imported from the `tractatus` package
- Extracted pure calc modules to `tractatus.calc`: `gex`, `gex_term_structure`, `vol`, `ma`, `oi`, `oi_zscore`, `iv_zscore`, `fixed_strike_vol`
- Refactored `gex_term_structure.compute_gex_term_structure` to accept `dict[date, DataFrame]` instead of `dict[date, Path]`
- `tractatus` installed as git dependency pinned to `main`

---

## Unreleased — feat/minio-s3-data-sources

### Added
- `src/options_monitor/tickrake/` — new module wrapping all tickrake I/O behind a `TickrakeClient` facade (`intraday`, `archive`, `filesystem` sub-clients)
- `bin/run_dev.sh` and `bin/run_docker.sh` — scripts that source `.env` and start the app locally or in Docker
- `.env.example` — configuration template
- `docs/ARCHITECTURE.md` — dated design decisions

### Changed
- Replaced tickrake SQLite `file_metadata_cache` index with MinIO intraday index JSON + per-expiry CSVs
- Historical options data now resolved via local `ROOT.json` + S3 download on cache miss, instead of SQLite
- AWS S3 credentials resolved via standard boto3 credential chain; `~/.aws` mounted read-only in Docker
- Dropped `OPTIONS_MONITOR_` prefix from all environment variables
- Docker default port changed from 8502 to 8503
- Fixed-strike vol table defaults to OTM contracts with 0DTE off

---

## 2026-06-27

### Added
- GEX history views via parquet (#9)
- Flow tab historical dates routed through parquet (#8)
- Fixed-strike vol z-score history via DuckDB parquet (#7)
- Open interest z-score table (#383eeca)

### Changed
- Parquet + DuckDB foundation replacing per-file CSV loading for historical data (#6)
- Downsampling parquet history by latest-per-bucket instead of modulo filter
- Per-day DTE buckets for 0–10 DTE; exclude near-expiry 0DTE samples

### Removed
- Dead CSV-era snapshot functions (#10)
- Underlying tab (#14)
