# Vol Regime observation cache

Status: implemented in Options Monitor development runtime.

- Store the two historical ATM IV and 25-delta risk reversal observations per
  symbol, sample date, and target DTE in SQLite. Retain them without age expiry.
- Keep the database under `OPTIONS_MONITOR_CACHE_DIR`, on a separate host mount
  from the Tractatus Parquet cache. SQLite is embedded in the app container.
- Validate a cached day against its source file size and modification time and
  the calculation version before using it. Recompute changed days.
- Read the latest published intraday option chain directly on each Vol Regime
  chart refresh, which runs every 30 seconds. Preserve the recent archived
  snapshot fallback when today's intraday data is unavailable.
- Verify with unit tests, UI smoke tests, and a cold/warm historical cache check
  inside the isolated development container.
