---
type: feature
tags: [tractatus, intraday-separation, duckdb]
title: "tractatus: Add OptionsQueryClient with DuckDB parquet querying"
description: Add OptionsQueryClient to tractatus to own all DuckDB parquet queries, removing raw SQL from options-monitor
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

options-monitor currently runs its own DuckDB queries directly against parquet files in `src/options_monitor/data/options.py`. These queries (snapshot lookup, expiry loading, time-bucketed lookback, latest archived window) belong in tractatus as the data-access library. This task adds `OptionsQueryClient` to tractatus, which options-monitor will then delegate to.

Also exports `OPTIONS_DTYPES` from this module as the single source of truth for column dtype casting shared between tractatus and options-monitor.

## Requirements

- Create `src/tractatus/tickrake/options/queries.py` with `OptionsQueryClient` class
- Constructor accepts optional `duckdb.DuckDBPyConnection`; defaults to `:memory:` when not injected
- Implement all 8 query methods:
  - `list_snapshot_times(parquet_path, expiry) -> list[datetime]`
  - `load_snapshot(parquet_path, expiry, sampled_at) -> pd.DataFrame`
  - `load_expiry(parquet_path, expiry) -> pd.DataFrame`
  - `load_lookback(parquet_glob, expiry_range, interval_minutes) -> pd.DataFrame` — time-bucketed deduplication
  - `load_sample_window(parquet_glob, sample_start, interval_minutes) -> pd.DataFrame`
  - `load_expiry_lookback(parquet_glob, expiry, interval_minutes) -> pd.DataFrame`
  - `latest_window(parquet_path, start_date, end_date) -> list[tuple[date, datetime]]`
  - `list_expirations(parquet_path, min_date) -> list[date]`
- Each method normalizes output via `_normalize_df` (cast dtypes, parse `expiration_date`, uppercase `contract_type`)
- Module exports `OPTIONS_DTYPES: dict[str, str]`
- Add `duckdb>=1.0` to `pyproject.toml` dependencies
- Expose `options_query` on `TickrakeClient` (see `tractatus_deprecate_intraday_client.md`)
- Full type annotations; passes `mypy` strict and `ruff` check

## Dependencies & Resources

- Must be committed to `main` before options-monitor Phase 2 work begins (options-monitor installs via `git+...@main`)
- Related: `tractatus_deprecate_intraday_client.md`, `tractatus_fix_list_roots_fallback.md`
- Queries to migrate from: `src/options_monitor/data/options.py` (lines ~155–350)
- Reference: `src/tractatus/tickrake/options/archive.py` for parquet path resolution pattern
