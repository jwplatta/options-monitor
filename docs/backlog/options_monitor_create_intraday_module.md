---
type: feature
tags: [options-monitor, intraday-separation]
title: "options-monitor: Create data/intraday.py — MinIO access module"
description: Extract all MinIO/boto3 intraday logic from data/options.py into a dedicated module owned by options-monitor
created: 2026-09-21
updated: 2026-09-21
status: complete
priority: high
source: claude/options-monitor
---

# Summary

options-monitor's `data/options.py` mixes MinIO intraday access with historical archive access. Since tractatus is being refactored to not know about intraday storage, options-monitor needs to own the MinIO access layer directly. This task creates `src/options_monitor/data/intraday.py` with an `IntradayStore` class and the same cached function API that callers (tabs) currently use.

## Requirements

- Create `src/options_monitor/data/intraday.py`:
  - `IntradayStore` class: wraps boto3 with connection params from options-monitor env vars
  - Methods on `IntradayStore`:
    - `fetch_index(root, provider) -> dict`
    - `fetch_csv(uri) -> pd.DataFrame`
    - `latest_snapshots(root, start_exp, end_exp, provider) -> dict[date, str]`
    - `list_expirations(root, provider) -> list[date]`
    - `list_roots(provider) -> list[str]` — scans MinIO index to return available symbol roots
    - `updated_at(root, provider) -> datetime | None`
  - Module-level cached functions (matching existing signatures from `data/options.py`):
    - `find_intraday_updated_at(symbol, _store) -> datetime | None`
    - `find_latest_snapshots(symbol, start_date, days_out, include_0dte, _store) -> dict[date, str]`
    - `list_expirations(symbol, _store) -> list[date]`
    - `load_options_snapshot(path_or_uri, _store) -> pd.DataFrame`
  - Connection params from env vars (same ones already used by tractatus `IntradayClient`): `MINIO_ENDPOINT`, `MINIO_BUCKET`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- Do NOT delete the corresponding functions from `data/options.py` yet — they will be re-exported from there for backward compat (handled in the `options.py` refactor task)
- Full type annotations; passes mypy strict and ruff

## Dependencies & Resources

- Depends on: tractatus Phase 1 complete (tractatus committed to main)
- Related: `options_monitor_refactor_options_py.md` (re-exports intraday functions from here)
- Reference implementation: `src/tractatus/tickrake/options/intraday.py` (same logic, different config source)
- File to refactor from: `src/options_monitor/data/options.py` — look for boto3/MinIO functions
