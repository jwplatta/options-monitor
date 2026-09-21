---
type: feature
tags: [intraday, minio, tractatus, flow]
title: Redesign intraday MinIO storage to publish full snapshot time series per expiry
description: Current MinIO index stores only the latest snapshot per expiry; flow charts need the full intraday time series
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

The current intraday MinIO data structure publishes one CSV per expiry containing a single point-in-time snapshot. This is sufficient for GEX and option chain views (which only need the latest state), but Flow Tape and Flow Profile require the full intraday time series to compute volume deltas between consecutive snapshots.

The redesign should publish all snapshots accumulated throughout the session, while still providing a clean way to access just the latest snapshot for views that don't need history.

## Requirements

### MinIO data structure (tractatus / tickrake publisher)

- Each expiry CSV should contain **all snapshots collected during the session**, with a `sampled_at` column (UTC timestamp) identifying each snapshot
- Alternatively, publish separate per-snapshot files under a time-series prefix (e.g. `intraday/schwab/timeseries/SPXW_exp2026-09-21/<timestamp>.csv`) and keep the single-file index pointing to the latest
- The index JSON should distinguish between `latest_uri` (single snapshot for GEX/chain views) and `series_uri` (full time series for flow views), or document a consistent naming convention

### options-monitor / IntradayStore

- Add `fetch_series_csv(root, expiry)` method to `IntradayStore` that loads the full time-series CSV for an expiry and returns a DataFrame with `sampled_at` as a proper datetime column
- Flow tab uses `fetch_series_csv` for today's data instead of local filesystem CSVs
- If MinIO is unreachable or no series data exists for the selected expiry, surface a clear error — do not fall back silently to local files

### Flow tab behavior

- Today's date: load time-series data from MinIO via `IntradayStore.fetch_series_csv`
- Historical dates: load from local parquet archive (unchanged)
- If MinIO series data is unavailable: show explicit error ("Intraday time series not available for this expiry")

## Dependencies & Resources

- `src/options_monitor/data/intraday.py` — add `fetch_series_csv` method
- `src/options_monitor/tabs/flow.py` — use `fetch_series_csv` for today's date
- tractatus tickrake publisher — must write `sampled_at` column and accumulate snapshots per session
- `docs/backlog/fix_flow_tab_no_snapshots.md` — related bug this supersedes
