---
type: bug
tags: [flow, intraday]
title: Flow tab shows "no snapshots found" on navigation
description: Navigating to the Flow tab displays a "no snapshots found" message instead of loading data
created: 2026-09-21
updated: 2026-09-21
status: not-started
priority: high
source: claude/options-monitor
---

# Summary

When navigating to the Flow tab, the UI reports that no snapshots are found rather than rendering flow data. It is unclear whether this is a data-loading issue (intraday MinIO not returning snapshots, archive fallback failing) or a UI/session-state issue (stale state from a previous tab causing incorrect symbol or date inputs).

## Requirements

- Identify whether the failure is in `find_latest_snapshots` (intraday path), the archive fallback, or the filesystem scan
- Confirm the selected symbol has snapshots available (check MinIO index and local archive)
- Verify `list_expirations` and `find_all_snapshots_for_expiry` return non-empty results for the symbol
- Fix the root cause and ensure the Flow tab loads correctly on first navigation

## Dependencies & Resources

- `src/options_monitor/tabs/flow.py` — tab entry point; imports `list_expirations`, `find_all_snapshots_for_expiry`, `list_snapshot_dates`
- `src/options_monitor/data/intraday.py` — `find_latest_snapshots`, `list_expirations`
- `src/options_monitor/data/options.py` — `find_all_snapshots_for_expiry`, `list_snapshot_dates`
