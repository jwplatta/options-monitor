# Architecture

## Data Routing

**Decision (2026-06-27):** Route data access by date — intraday vs. historical have fundamentally different storage characteristics.

- **Today (intraday):** Option chain CSVs are still being written by tickrake scrapers. Read the latest snapshot per expiry directly from MinIO via the intraday index JSON. For time-series replay (Flow / History tabs), scan local timestamped CSVs — MinIO only retains the latest snapshot per expiry.
- **Historical (any prior date):** Read from daily compacted parquet files. Check local cache first (`~/.tickrake/data/options/schwab/YYYY/MM/DD/`); download from S3 on cache miss.

## Storage Format: Parquet for Historical Data

**Decision (2026-06-27):** Use parquet for all historical options data.

Benchmark on 2026-06-26 SPXW data: 5,759 CSVs (479 MB) → 1 parquet file (77 MB). Load time 14,064ms → 241ms — **58x faster, 6x smaller.**

The compression wins are structural: columnar storage encodes repeated strikes and expiries once; binary numeric storage eliminates ASCII parsing; Snappy compression works well on already-repetitive columnar data.

## Query Layer: DuckDB

**Decision (2026-06-27):** Use DuckDB as the query layer on top of parquet.

DuckDB is embedded (no server), natively columnar, and can query parquet files directly without importing. It pushes filter predicates into parquet scans so only needed rows and columns are deserialized. Critically, it returns pandas DataFrames via `.df()` — zero changes to the existing pandas/plotly calc layer.

Alternatives considered and rejected: Polars (faster but requires rewriting entire calc layer), MotherDuck (cloud overhead), Lance/LanceDB (immature), ClickHouse (requires server process).

## Intraday Source: MinIO

**Decision (2026-09-14):** Replace tickrake's SQLite `file_metadata_cache` as the intraday metadata index with MinIO directly.

The SQLite dependency coupled options_monitor tightly to tickrake internals. MinIO exposes a stable S3-compatible API — the intraday index JSON (`intraday/schwab/{ROOT}.json`) is the canonical source of truth for what's available right now, and per-expiry CSVs are fetched on demand.

## AWS Credentials

**Decision (2026-09-14):** No explicit AWS credentials in config. Rely on the standard boto3 credential chain (`~/.aws/credentials`, IAM role, environment). In Docker, `~/.aws` is mounted read-only into the container.

## tickrake Module Boundary

**Decision (2026-09-14):** All tickrake I/O is isolated in `src/options_monitor/tickrake/`. The `TickrakeClient` facade (intraday + archive + filesystem sub-clients) is the only interface the rest of the app uses. This boundary is intentional — the module is designed to be extracted as a standalone package if needed.
