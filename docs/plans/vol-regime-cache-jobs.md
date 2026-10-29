---
date_created: 2026-10-28
description: Dashboard cache implementation and current option-root configuration design.
---

# Dashboard cache and configuration plan

## Pull requests
1. Independent chart symbol selectors (merged #32).
2. Shared cache/job infrastructure and Vol Regime (PR #33); Tractatus API prerequisite #39.
3. Vol Skew using the same cache/job pattern.
4. Fixed Strike Vol with measured incremental aggregation.

## Root registry and settings
- The committed `src/options_monitor/config/option_roots.yaml` is the supported-root source of truth. Each entry requires option_root and underlying; additional JSON-compatible fields become per-row metadata.
- The SQLite option_roots table has option_root, underlying, namespace_id, refreshed_at, last_error and metadata_json; PK(namespace_id,option_root), index(option_root).
- Seed after database creation/reset, and sync on restart. Upsert changed entries and remove entries deleted from YAML; unchanged rows keep timestamps. Validate before touching existing caches. Never scan MinIO for roots; no refresh button or root job.
- Registry reconciled against the 2026-10-29 historical bucket inventory; index underlying mappings match Tractatus normalization. It is packaged with the app, not read from another repo at runtime.
- Sidebar page is Settings. A separate shared warmup list is persisted in SQLite, initially empty; each chart job uses that list and its own parameters. Configured roots are not automatically warmed.

## Historical cache contract
- Use Tractatus CacheReader for historical source inventories/revisions and projected reads from tractatus-lakehouse. This remains independent of configured-root discovery.
- Store computed ATM IV and 25-delta risk reversal per selected daily snapshot, not option chains. Each day selects its nearest target-DTE expiry, first sample at/after 10:30 New York, and closing sample; deduplicate identical timestamps.
- Bulk-read historical metric ranges from SQLite, excluding the current comparison day. Reuse sorted distributions in memory and compare with fresh intraday metrics. Preserve the recent archived-close fallback.
- Namespace by endpoint/bucket/provider and invalidate source replacements using ETag/size revisions. No manual calculation versions: reset the cache after formula/sampling changes.
- All current table/index definitions live in data/sqlite_cache.py. No migrations or schema versions. Incompatible schemas atomically rebuild the disposable database, including saved settings; configured roots are seeded again automatically.

## Jobs and retirement
- One bounded in-process worker owns task-local reader/query connections. Deduplicate requests, prioritize user work, persist status/retries, and recover interrupted jobs.
- Warmup and non-watchlist requests use the same daily metrics. On-demand requests do not join the shared warmup list.
- Historical refresh interval: fifteen minutes. Retry failures from 30 seconds with exponential backoff capped at fifteen minutes. Retain the last successful data on failure.
- Default retention: 365 calendar days, configurable for each chart. Daily cleanup plus startup catch-up removes strictly older observations, cascades dependencies, and invalidates distributions. Honor retention during reads and refresh to prevent rehydrating expired data.
- Calendar-date timezone: OPTIONS_MONITOR_TIMEZONE, default America/Chicago. Persist timestamps in UTC. Snapshot selection remains 10:30 New York.

## Validation and measurements
- Test root YAML validation, metadata preservation, seeding after reset, restart config edits/removals, namespace separation, packaged YAML and local dropdowns.
- Test real metric correctness, revision changes, valid empty days, request deduplication/priority, retries/restart, cleanup boundaries, schema rebuild and concurrent initialization.
- Frozen real SPXW fixture: 45 rows, four dates, eight snapshots. Fixed Decimal reference values cover ATM IV, both 25-delta IVs, RR and cached percentiles excluding the current day.
- Live 30-day / 12-session measurements: SPXW cold compute 3.400 s, unchanged refresh 0.815 s, SQLite range 0.192 ms; TSLA 1.171 s / 0.833 s / 0.129 ms. Both produced 24 IV and 24 RR observations. In-memory distribution lookups averaged about 0.004 ms.
- Timings exclude live reads/rendering and are not a multi-user guarantee. Source history ended October 16; coverage is independently warned about. Warm history must perform no synchronous historical remote scans; initial local target is under 100 ms per symbol.
- Dev cache defaults to ~/.cache/options-monitor-dev; production keeps its separate path. Restart dev after worker/schema changes to stop old hot-reloaded threads. Production services were not restarted.

## Historical bucket root reconciliation (2026-10-29)

One-time CacheReader listing of tractatus-lakehouse, schwab provider: 144 roots. All are now explicitly configured in YAML. Index mappings were checked against Tractatus normalization. Existing configured roots without historical objects were retained: ANSS, DAY, GOOGLE. Runtime still uses only committed YAML and does not scan the bucket.

```text
AAPL ACN ADBE ADI ADP ADSK AMAT AMD AMZN ANET ARKK ARM ASTS AVGO BAC CAT CDNS CLSK COIN COST
CRM CRWD CRWV CSCO CVNA CVX DELL DIA DJX DJXW DKNG DRAM DXC EEM EFA EPAM FICO FTNT FXI GEN GLD
GME GOOG GOOGL GPN HD HOOD HPE HPQ HYG IBM IEF IJR INTC INTU IT ITA IWD IWF IWM JNK JPM KLAC
KRE LLY LQD LRCX MA MARA MCHP MDY META MPWR MRVL MSCI MSFT MSTR MU NDX NDXP NFLX NOW NTAP NVDA
NXPI ON ORCL PANW PAYC PAYX PLTR PYPL QCOM QQQ RBLX RIVN RSP RUT RUTW SBUX SCHW SHY SLV SMCI
SMH SNAP SNPS SOFI SOXL SPCX SPX SPXW SPY STX SWKS TAN TER TIP TLT TSLA TXN UBER UNH V VIX VIXW
WDC WMT XBI XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY XOM XOP XRT XSP
```
