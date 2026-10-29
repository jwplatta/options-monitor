---
date_created: 2026-10-28
description: Incremental dashboard cache implementation, beginning with Vol Regime.
---

# Dashboard historical cache and warmup plan

## Pull requests
1. Independent chart symbol selectors (merged #32).
2. Shared SQLite/job infrastructure and Vol Regime (this work), with a prerequisite Tractatus CacheReader API PR.
3. Vol Skew on the same job/cache pattern.
4. Fixed Strike Vol with measured incremental aggregation.

## Contract
Use CacheReader for historical discovery and projected reads from tractatus-lakehouse. Store computed historical ATM IV and 25-delta risk reversal, not chains. Select the expiry nearest the requested DTE independently for each market date, then the first sample at/after 10:30 New York and the last sample; deduplicate coincident timestamps. Historical metrics exclude the current comparison date. Current values remain fresh intraday reads with the existing recent archive fallback.

All current SQLite DDL, indexes and constraints live in data/sqlite_cache.py. Rebuild incompatible disposable databases without versioning or migrations. Namespace by endpoint/bucket/provider; invalidate daily results with source ETag/size revision and calculation version. Cache valid empty days. Atomically replace daily observations and increment a generation for in-memory range distributions.

## Repeatable jobs
Register job ID, calculation version, canonical parameters, compute function, defaults, refresh interval and retention. One bounded in-process worker owns its reader/connection. Deduplicate jobs, prioritize user requests, persist status/retries/watchlists, recover interrupted work, and serve previous successful results during refresh. On-demand symbols cache normally without joining the warmup list. Metadata refresh: five minutes; historical refresh: fifteen minutes. Failed discovery preserves prior data.

Persist watchlist and retention settings in SQLite, editable through dashboard settings. Default warmup: empty shared list; Vol Regime defaults to 30 DTE. Default retention: 365 calendar days; configurable per job. Daily cleanup with startup catch-up removes strictly older dates, invalidates distributions, and prevents rehydration outside retention. Retry after 30 seconds, doubling to fifteen minutes. No raw chains or final live percentiles in SQLite.

## Schemas
cache_namespaces: namespace_id PK, endpoint, historical_bucket, provider; unique source identity.
cache_sources: namespace_id/root/sample_date PK, uri, revision, size_bytes, checked_at.
cache_job_state: job_id/namespace_id/root/params_json PK, calc_version, status, request/start/completion/access/retry times, attempt_count, last_error.
cache_warmup_targets: job_id/namespace_id/root/params_json PK, enabled, position. Shared-list entries use job_id `*` and empty parameters; per-chart warmup parameters live in cache_settings. Legacy per-chart lists are ignored.
cache_metadata: namespace_id/metadata_key PK, payload_json, refreshed_at, last_error.
cache_settings: setting_key PK, value_json, updated_at.
cache_generations: namespace_id/job_id/root PK, generation.
vol_regime_days: namespace_id/root/sample_date/target_dte PK, calc_version, source_revision, selected_expiry, computed_at, outcome.
vol_regime_observations: namespace_id/root/sample_date/target_dte/sampled_at PK, atm_iv, risk_reversal; cascading parent day FK.

## Acceptance
Measure cold/warm preparation and MinIO requests before tuning. Warm history must use bulk SQLite reads without synchronous historical MinIO work. Validate computation parity, same-URI replacement, empty days, new dates, retries, restart, concurrency, cleanup boundaries and non-watchlist reuse. Record measured timings, full checks and live verification separately. Do not migrate Skew/Fixed Strike in this PR.

## Implementation and measured validation

Prerequisite: Tractatus PR https://github.com/jwplatta/tractatus/pull/39. Dashboard pins its exact commit; merge the prerequisite first. Public APIs are `list_option_sources`, `option_daily_snapshots`, `query_connection`, and `configure_connection`. Root discovery now uses a shallow delimiter listing, avoiding traversal of intraday snapshot objects.

Live dev-container measurements on 2026-10-28, isolated SQLite database, 30-calendar-day range / 30 DTE:

| Root | Sessions | IV/RR observations | Cold compute | Unchanged refresh | SQLite range read | In-memory distribution lookup |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SPXW | 12 | 24 / 24 | 3.400 s | 0.815 s | 0.192 ms | 0.0040 ms |
| TSLA | 12 | 24 / 24 | 1.171 s | 0.833 s | 0.129 ms | 0.0036 ms |

Cold compute includes inventory and projected reads. Unchanged refresh rechecks inventory but skips chain queries. The benchmark reports source object sizes, not measured wire traffic. Timings exclude current intraday retrieval and Plotly rendering; filesystem/MinIO caches may already be warm. The historical sources end on October 16, which remains a source coverage issue, independently warned about in the chart.

Warm preparation acceptance: no synchronous historical MinIO operations, with an initial local target of under 100 ms per symbol for SQLite/distribution preparation. These results satisfy the single-symbol target; they do not establish a multi-user latency guarantee. Streamlit AppTest against live data rendered an SPXW Plotly chart with zero exceptions after the worker reached ready. It exercised controls and exposed retention/source-coverage warnings.

Dev Compose now defaults to a separate `~/.cache/options-monitor-dev` directory to prevent dev cache rebuilds from affecting production. Live verification used `/tmp/options-monitor-vol-regime-dev` and `TRACTATUS_SRC=/tmp/tractatus-dashboard-cache/src`; those are session-specific mounts. After merging Tractatus, update its normal local checkout before recreating dev with `make dev-shared`. Production services were not restarted.

Current schema definitions omit obsolete tables. Tests verify automatic rebuilding of incompatible caches and preservation of contents when definitions match. Cleanup uses the configurable dashboard date (`OPTIONS_MONITOR_TIMEZONE`, default `America/Chicago`), cascades to observations, and runs once daily plus startup catch-up. Changing retention schedules cleanup again and makes completed jobs eligible to refresh.

Final checks before PR: Options Monitor `make check` passed (149 unit tests, Ruff, format, mypy, gitleaks); Tractatus `make check` passed (136 tests, Ruff, format, mypy). The root-discovery live smoke check initially exposed a recursive-listing stall; the prerequisite PR fixes it with delimiter-based index discovery, and the subsequent Streamlit check rendered successfully. No full-browser or load/concurrency benchmark was performed.

Cache controls are now on the dedicated **Cache Settings** sidebar page, initially with a Vol Regime section. Additional chart sections can be added there in later PRs.

Schema maintenance update: current DDL only, no schema versions or migration chain. On open, incompatible table/index definitions cause an atomic cache rebuild, including stored settings. Matching schemas preserve contents. Obsolete tables are not part of the current definitions.

Calculation-version update: Vol Regime and shared jobs no longer carry manual version constants or columns. Remote revision changes still invalidate observations. Formula/sampling changes require stopping the app and discarding its cache before recomputing, even if the SQLite schema is unchanged.

Real-data regression coverage: 45 captured SPXW chain rows from October 12–15, 2026, eight daily-selected snapshots. Sources and independent Decimal reference calculations are documented in tests/fixtures/vol_regime. Tests check ATM IV, both interpolated 25-delta IVs, RR, persisted metrics and a six-observation historical percentile comparison excluding the current day. Full checks pass with 167 tests.
