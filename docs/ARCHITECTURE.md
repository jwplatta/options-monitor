# Architecture

## 2026-09-14

### Replace SQLite with MinIO for intraday data
Tickrake's SQLite `file_metadata_cache` was the metadata index for intraday option chains. This coupled options_monitor tightly to tickrake internals. Replaced with MinIO directly — the intraday index JSON (`intraday/schwab/{ROOT}.json`) is the canonical source of what's available right now, and per-expiry CSVs are fetched on demand via the S3 API.

### tickrake module boundary
All tickrake I/O is isolated in `src/options_monitor/tickrake/`. The `TickrakeClient` facade (intraday + archive + filesystem sub-clients) is the only interface the rest of the app uses. This boundary is intentional — the module is designed to be extracted as a standalone package if needed. See [tickrake](https://github.com/jwplatta/tickrake).

### AWS credentials via credential chain
No explicit AWS credentials in config. Rely on the standard boto3 credential chain (`~/.aws/credentials`, IAM role, environment). In Docker, `~/.aws` is mounted read-only into the container.

---

## 2026-06-27

### Data routing rule: intraday vs. historical
Route data access by date — intraday and historical have fundamentally different storage characteristics.

- **Today (intraday):** CSVs are still being written by tickrake scrapers. Read the latest snapshot per expiry from MinIO. For time-series replay (Flow / History tabs), scan local timestamped CSVs — MinIO only retains the latest snapshot per expiry.
- **Historical:** Read from daily compacted parquet files. Check local cache first (`~/.tickrake/data/options/schwab/YYYY/MM/DD/`); download from S3 on cache miss.

### Parquet for historical data
Benchmark on 2026-06-26 SPXW data: 5,759 CSVs (479 MB) → 1 parquet file (77 MB). Load time 14,064ms → 241ms — **58x faster, 6x smaller.** Columnar storage encodes repeated strikes and expiries once; binary numeric storage eliminates ASCII parsing; compression works well on repetitive columnar data.

### DuckDB as the query layer
DuckDB is embedded (no server), natively columnar, and queries parquet files directly without importing. It pushes filter predicates into parquet scans so only needed rows and columns are deserialized, and returns pandas DataFrames via `.df()` — zero changes to the existing pandas/plotly calc layer.

Alternatives considered and rejected: Polars (faster but requires rewriting the entire calc layer), MotherDuck (cloud overhead), Lance/LanceDB (immature), ClickHouse (requires a server process).
