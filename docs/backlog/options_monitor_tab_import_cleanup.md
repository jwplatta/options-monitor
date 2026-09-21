---
type: chore
tags: [options-monitor, intraday-separation]
title: "options-monitor: Tab import cleanup — remove re-exports, update direct imports"
description: After intraday module is stable, remove backward-compat re-exports from options.py and update tab imports to use data.intraday directly
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: medium
source: claude/options-monitor
---

# Summary

After `data/intraday.py` is created and `data/options.py` refactored, the intraday functions are temporarily re-exported from `options.py` for backward compat. This follow-up task removes those re-exports and updates all tab imports to use `data.intraday` directly.

This is a pure cleanup — no behavior changes.

## Requirements

- Remove re-export block from `src/options_monitor/data/options.py`:
  ```python
  from options_monitor.data.intraday import (
      find_intraday_updated_at, find_latest_snapshots, list_expirations, load_options_snapshot
  )
  ```
- Update import sites in tabs to use `from options_monitor.data.intraday import ...`:
  - `src/options_monitor/tabs/gex.py`
  - `src/options_monitor/tabs/oi.py`
  - `src/options_monitor/tabs/flow.py`
  - Any other tab or module importing intraday functions from `data.options`
- `uv run ruff check src tests` — clean
- `uv run mypy src` — no errors
- `uv run pytest tests/unit/` — all pass

## Dependencies & Resources

- Depends on: `options_monitor_refactor_options_py.md` complete and stable in production
- Files: `src/options_monitor/tabs/gex.py`, `tabs/oi.py`, `tabs/flow.py`, `data/options.py`
