"""Time the actual Vol Regime computation for several option roots.

Examples:
  uv run --env-file .env python scripts/benchmark_vol_regime.py \
      --endpoint http://localhost:9000 --lookback-days 360
  uv run --env-file .env python scripts/benchmark_vol_regime.py --as-of today

The default as-of date is each root's latest archived date. This exercises the
historical path even when the archive is stale relative to the wall clock.
Cached Streamlit functions are cleared before each root; downloaded Parquet
files remain on disk, so repeat runs show a warm file-cache comparison.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from contextlib import ExitStack
from unittest.mock import patch

from benchmark_vol_common import (
    DEFAULT_SYMBOLS,
    Timings,
    benchmark_date,
    cache_stats,
    format_bytes,
    frozen_date,
)

os.environ["DUCKDB_OPTIONS_PATH"] = ":memory:"
logging.disable(logging.WARNING)

from options_monitor.data.reader import get_reader  # noqa: E402
from options_monitor.tabs.vol import vol_regime  # noqa: E402


def _clear_dashboard_caches() -> None:
    for fn in (
        vol_regime._compute_vol_regime_data,
        vol_regime._pick_expiry_from_parquet,
        vol_regime._load_eod_snapshot_for_expiry,
        vol_regime._load_daily_snapshots_for_expiry,
        vol_regime.find_latest_snapshots,
        vol_regime.load_options_snapshot,
    ):
        fn.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--target-dte", type=int, default=30)
    parser.add_argument("--as-of", default="latest", help="latest, today, or YYYY-MM-DD")
    parser.add_argument("--endpoint", help="Override MINIO_ENDPOINT (use localhost from the host)")
    parser.add_argument("--cache-dir", help="Override TRACTATUS_CACHE_DIR for cold-cache runs")
    args = parser.parse_args()
    if args.lookback_days < 1 or args.target_dte < 0:
        parser.error("lookback-days must be positive and target-dte must be nonnegative")

    if args.endpoint:
        os.environ["MINIO_ENDPOINT"] = args.endpoint
    if args.cache_dir:
        os.environ["TRACTATUS_CACHE_DIR"] = args.cache_dir
    reader_started = time.perf_counter()
    reader = get_reader()
    print(f"Reader initialization: {time.perf_counter() - reader_started:.2f}s")
    print(f"MinIO endpoint: {reader._cfg.minio_endpoint}")
    successful = 0
    for symbol in dict.fromkeys(s.upper() for s in args.symbols):
        print(f"\n{symbol}: discovering available dates...", flush=True)
        try:
            discovery_start = time.perf_counter()
            dates = reader.list_sample_dates(symbol)
            discovery_seconds = time.perf_counter() - discovery_start
            if not dates:
                print(f"  No archived dates ({discovery_seconds:.2f}s)")
                continue
            as_of = benchmark_date(args.as_of, dates[-1])
            before_count, before_bytes = cache_stats(reader._cfg.cache_dir, symbol)
            print(
                f"  as-of={as_of} latest={dates[-1]} dates={len(dates)} "
                f"discovery={discovery_seconds:.2f}s "
                f"cached-before={before_count} files/{format_bytes(before_bytes)}",
                flush=True,
            )

            _clear_dashboard_caches()
            timings = Timings()
            with ExitStack() as stack:
                stack.enter_context(patch.object(vol_regime, "date", frozen_date(as_of)))
                for obj, attr, label in (
                    (reader, "list_sample_dates", "manifest date listing"),
                    (reader, "get_parquet", "resolve/download parquet"),
                    (reader, "ensure_parquet_range", "cache historical range"),
                    (vol_regime, "find_latest_snapshots", "find live snapshots"),
                    (vol_regime, "load_options_snapshot", "load live snapshot"),
                    (vol_regime, "_pick_expiry_from_parquet", "pick historical expiry"),
                    (vol_regime, "_load_eod_snapshot_for_expiry", "load current EOD chain"),
                    (vol_regime, "_load_daily_snapshots_for_expiry", "load daily chains"),
                    (vol_regime, "compute_atm_iv", "compute ATM IV"),
                    (vol_regime, "compute_risk_reversal", "compute risk reversal"),
                ):
                    timings.patch(stack, obj, attr, label)
                started = time.perf_counter()
                result = vol_regime._compute_vol_regime_data(
                    (symbol,), args.target_dte, args.lookback_days
                )
                elapsed = time.perf_counter() - started

            after_count, after_bytes = cache_stats(reader._cfg.cache_dir, symbol)
            print(
                f"  result={len(result)} rows total={elapsed:.2f}s "
                f"cached-after={after_count} files/{format_bytes(after_bytes)} "
                f"added={format_bytes(after_bytes - before_bytes)}"
            )
            if not result.empty:
                row = result.iloc[0]
                print(
                    f"  IV samples={row['iv_history_count']} "
                    f"RR samples={row['rr_history_count']} "
                    f"history-through={row['history_through']}"
                )
            else:
                print("  No result; check archive freshness and current-chain coverage.")
            timings.print()
            successful += 1
        except Exception as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}")

    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
