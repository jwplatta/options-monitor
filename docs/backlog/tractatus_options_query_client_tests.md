---
type: chore
tags: [tractatus, intraday-separation, duckdb, testing]
title: "tractatus: Unit tests for OptionsQueryClient"
description: Full unit test coverage for the new OptionsQueryClient using real in-memory parquet files
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

After `OptionsQueryClient` is implemented, add thorough unit tests in tractatus. Tests should use real DuckDB against real in-memory parquet files (no mocking) so they validate actual SQL behavior.

## Requirements

- Create `tests/test_options_queries.py` in tractatus
- Build test parquet files using pyarrow in `tmp_path` (same pattern as existing conftest)
- One test per public method, plus edge cases:
  - `test_list_snapshot_times_returns_sorted_datetimes`
  - `test_load_snapshot_filters_by_expiry_and_sampled_at`
  - `test_load_expiry_returns_all_rows_ordered_by_sampled_at`
  - `test_load_lookback_deduplicates_within_interval_bucket`
  - `test_load_sample_window_filters_by_start_date`
  - `test_load_expiry_lookback_single_expiry`
  - `test_latest_window_returns_max_sampled_at_per_expiry`
  - `test_list_expirations_returns_only_dates_gte_min`
  - `test_empty_parquet_returns_empty_list_or_dataframe` (each method)
  - `test_normalize_df_uppercases_contract_type`
- No mocking of DuckDB — use real DuckDB against real files
- All tests pass under `uv run pytest tests/test_options_queries.py`

## Dependencies & Resources

- Depends on: `tractatus_add_options_query_client.md`
- Reference: existing conftest.py in tractatus for pyarrow fixture patterns
