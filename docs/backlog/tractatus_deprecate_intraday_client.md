---
type: chore
tags: [tractatus, intraday-separation]
title: "tractatus: Deprecate IntradayClient on TickrakeClient"
description: Remove intraday/MinIO knowledge from tractatus by deprecating IntradayClient and exposing OptionsQueryClient
created: 2026-09-21
updated: 2026-09-21
status: complete
priority: high
source: claude/options-monitor
---

# Summary

tractatus should not know about intraday MinIO storage — that is an application-level concern. `IntradayClient` (in `src/tractatus/tickrake/options/intraday.py`) needs to be deprecated from `TickrakeClient`. The class itself stays temporarily (for backward compatibility) but accessing it via `TickrakeClient.options_intraday` emits a `DeprecationWarning`. `OptionsQueryClient` is added as the new `options_query` attribute.

## Requirements

- In `src/tractatus/tickrake/client.py`:
  - Convert `self.options_intraday` from a direct attribute to a `@property` that emits `DeprecationWarning` before returning `self._options_intraday`
  - Add `self.options_query = OptionsQueryClient(conn)` where `conn` is an optional `duckdb.DuckDBPyConnection` accepted by `TickrakeClient.__init__`
- `TickrakeClient.__init__` signature: `def __init__(self, cfg: TickrakeConfig | None = None, query_conn: duckdb.DuckDBPyConnection | None = None) -> None`
- `IntradayClient` itself is NOT deleted — just deprecated. Deletion is a follow-up after options-monitor is fully migrated.
- Full type annotations; passes mypy strict

## Dependencies & Resources

- Depends on: `tractatus_add_options_query_client.md`
- Related: `options_monitor_create_intraday_module.md` (options-monitor takes over intraday ownership)
- File: `src/tractatus/tickrake/client.py`
