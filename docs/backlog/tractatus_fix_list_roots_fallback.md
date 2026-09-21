---
type: bug
tags: [tractatus, intraday-separation, symbol-discovery]
title: "tractatus: Fix FilesystemClient.list_roots() to fall back to filesystem scan"
description: list_roots() only reads tickers.json — if absent or empty, options-monitor shows only SPXW
created: 2026-09-21
updated: 2026-09-21
status: complete
priority: high
source: claude/options-monitor
---

# Summary

`FilesystemClient.list_roots()` in tractatus reads only `~/.tickrake/data/options/schwab/tickers.json`. If that file is missing or its `roots` array is empty, the method returns `[]`. options-monitor's `_available_roots()` then falls back to `["SPXW"]`, hiding all other available symbols.

Other similar clients (`CandlesClient.list_symbols()`, `LevelOneClient.list_symbols()`) dynamically scan the filesystem when static index files are absent. `list_roots()` should do the same.

## Requirements

- In `src/tractatus/tickrake/options/filesystem.py`, update `list_roots()`:
  1. Try `tickers.json` first (existing behavior — keep it)
  2. If `tickers.json` is missing or its `roots` list is empty, fall back to globbing `{provider_options_dir}/*.json` and returning the stems (excluding `"tickers"`)
- Resulting signature unchanged: `def list_roots(self, provider: str = "schwab") -> list[str]`
- Returns a sorted list; returns `[]` only if both sources are empty
- No new dependencies required

**Reproduction:**
1. Rename/remove `~/.tickrake/data/options/schwab/tickers.json`
2. Run options-monitor — only SPXW appears in symbol dropdown
3. After fix: root names discovered from per-symbol JSON index files (e.g. `SPXW.json`, `SPX.json`)

## Dependencies & Resources

- Related: `options_monitor_update_app_symbol_discovery.md` (options-monitor side: also query intraday store)
- File: `src/tractatus/tickrake/options/filesystem.py` — `list_roots()` method
- Reference pattern: `src/tractatus/tickrake/candles.py` `list_symbols()` for dynamic scan approach
