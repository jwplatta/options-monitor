---
type: chore
tags: [options-monitor, intraday-separation, duckdb]
title: "options-monitor: Refactor data/options.py — remove raw DuckDB, delegate to tractatus"
description: Remove module-level DuckDB connection and raw SQL from options.py; delegate archive queries to TickrakeClient.options_query; re-export intraday functions from intraday.py
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

`src/options_monitor/data/options.py` currently owns a module-level DuckDB connection and runs raw SQL queries against parquet files. This task refactors it so those queries are delegated to `TickrakeClient.options_query` (the new `OptionsQueryClient` from tractatus). The MinIO intraday functions are moved to `data/intraday.py` and re-exported from here for backward compat. Also updates `app.py` to construct and inject the DuckDB connection.

## Requirements

**Remove from `data/options.py`:**
- Module-level `_DUCKDB_CONN = duckdb.connect(...)` setup block (5 lines)
- `duckdb` import
- `_OPTIONS_DTYPES` dict (import from `tractatus.tickrake.options.queries` instead)

**Replace 6 DuckDB query functions with thin wrappers over `TickrakeClient.options_query`:**
- `find_historical_snapshot_times` → `client.options_query.list_snapshot_times`
- `load_historical_snapshot` → `client.options_query.load_snapshot`
- `load_historical_expiry` → `client.options_query.load_expiry`
- `load_historical_lookback` → `client.options_query.load_lookback`
- `load_historical_sample_window` → `client.options_query.load_sample_window`
- `load_historical_expiry_lookback` → `client.options_query.load_expiry_lookback`

**Keep 3 compound functions** (they orchestrate archive + query client together):
- `load_latest_archived_window` — updated to use `options_query.latest_window` + `options_query.load_snapshot`
- `list_expirations_from_archive` — updated to use `options_query.list_expirations`
- `load_latest_archived_single_expiry` — updated to use `options_query.list_snapshot_times` + `options_query.load_snapshot`

**Re-export intraday functions** for backward compat (tabs don't need to change yet):
```python
from options_monitor.data.intraday import (
    find_intraday_updated_at,
    find_latest_snapshots,
    list_expirations,
    load_options_snapshot,
)
```

**Update `app.py`:**
- Construct `duckdb.connect(DUCKDB_OPTIONS_PATH)` with all settings (memory_limit, threads, temp_directory)
- Pass `query_conn=conn` to `TickrakeClient(cfg, query_conn=conn)` so a single connection is shared
- Construct `IntradayStore` from env vars and store in session/module scope for data functions to use

**Tests:**
- Update `tests/unit/test_options_loader.py`: fix cache-clearing fixtures to also clear caches defined in `data/intraday.py`; move boto3 mock setup out of `_make_client` helper into intraday-specific helpers
- Add `tests/unit/test_intraday.py`: test `IntradayStore` methods with mocked boto3

## Dependencies & Resources

- Depends on: `options_monitor_create_intraday_module.md`, tractatus Phase 1 merged to main
- File: `src/options_monitor/data/options.py`
- File: `src/options_monitor/app.py`
- File: `tests/unit/test_options_loader.py`
