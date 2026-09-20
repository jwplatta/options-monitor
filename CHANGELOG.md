# Changelog

## Unreleased

### Changed
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
