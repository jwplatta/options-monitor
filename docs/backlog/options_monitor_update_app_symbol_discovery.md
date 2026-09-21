---
type: bug
tags: [options-monitor, intraday-separation, symbol-discovery]
title: "options-monitor: Merge archive + intraday symbol lists in _available_roots()"
description: _available_roots() only queries the archive filesystem; it should also query the intraday MinIO store so all available symbols appear
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

`_available_roots()` in `app.py` currently calls `TickrakeClient.options_filesystem.list_roots()` which reads only the archive filesystem. Symbols available in the live intraday MinIO store but absent from the archive (or when `tickers.json` is stale/missing) won't appear in the symbol dropdown, causing the app to fall back to `["SPXW"]` only.

After `data/intraday.py` is created with `IntradayStore.list_roots()`, this function should merge both sources.

## Requirements

- In `src/options_monitor/app.py`, update `_available_roots()`:
  ```python
  @st.cache_data(ttl=3600)
  def _available_roots() -> list[str]:
      archive_roots = _default_client().options_filesystem.list_roots()
      intraday_roots = _intraday_store().list_roots()  # gracefully returns [] on MinIO failure
      combined = sorted(set(archive_roots) | set(intraday_roots))
      return combined if combined else [_DEFAULT_SYMBOL]
  ```
- `IntradayStore.list_roots()` must exist (implemented in `options_monitor_create_intraday_module.md`)
- If MinIO is unreachable, `list_roots()` returns `[]` (graceful — same pattern as other intraday methods)
- Also ensure `FilesystemClient.list_roots()` fix is in place (see `tractatus_fix_list_roots_fallback.md`) so archive fallback works too

**Reproduction:**
1. Start options-monitor with `tickers.json` missing from `~/.tickrake/data/options/schwab/`
2. Only "SPXW" appears in symbol dropdown despite other symbols being live in MinIO

## Dependencies & Resources

- Depends on: `options_monitor_create_intraday_module.md`, `tractatus_fix_list_roots_fallback.md`
- File: `src/options_monitor/app.py` — `_available_roots()` function
