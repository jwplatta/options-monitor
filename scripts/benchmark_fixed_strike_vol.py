"""Time Fixed Strike Vol's historical downsampling and z-score preparation.

Examples:
  uv run --env-file .env python scripts/benchmark_fixed_strike_vol.py \
      --endpoint http://localhost:9000 --lookback-days 90

The historical query is the same one used by the dashboard. By default each
root is anchored to its latest archived date so stale archives can be profiled.
Downloaded Parquet files remain cached between runs. Use --as-of today to
reproduce the dashboard's exact date window.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable
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

from options_monitor.data import options  # noqa: E402
from options_monitor.data.reader import get_reader  # noqa: E402
from options_monitor.tabs.vol import fixed_strike  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--as-of", default="latest", help="latest, today, or YYYY-MM-DD")
    parser.add_argument("--endpoint", help="Override MINIO_ENDPOINT (use localhost from the host)")
    parser.add_argument("--cache-dir", help="Override TRACTATUS_CACHE_DIR for cold-cache runs")
    args = parser.parse_args()
    if args.lookback_days < 1 or args.interval_minutes < 1:
        parser.error("lookback-days and interval-minutes must be positive")

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

            fixed_strike._load_historical_frames.clear()
            options.load_historical_sample_window.clear()
            timings = Timings()
            raw_query = reader.options_query.load_sample_window
            with ExitStack() as stack:
                clock = frozen_date(as_of)
                stack.enter_context(patch.object(fixed_strike, "date", clock))
                stack.enter_context(patch.object(options, "date", clock))
                for obj, attr, label in (
                    (reader, "list_sample_dates", "manifest date listing"),
                    (reader, "get_parquet", "resolve/download parquet"),
                    (reader, "ensure_parquet_range", "cache historical range"),
                    (reader.options_query, "load_sample_window", "DuckDB dashboard query"),
                ):
                    timings.patch(stack, obj, attr, label)
                started = time.perf_counter()
                try:
                    frames, sample_times = fixed_strike._load_historical_frames(
                        symbol, args.lookback_days, args.interval_minutes
                    )
                except Exception as exc:
                    if "multiple '**'" not in str(exc):
                        raise
                    print(
                        f"  Dashboard query failed: {exc.__class__.__name__}: "
                        f"{str(exc).splitlines()[0]}"
                    )
                    print("  Retrying with a single recursive ** glob over cached files...")
                    corrected_glob = str(
                        reader._cfg.cache_dir
                        / "options"
                        / "schwab"
                        / "**"
                        / f"{symbol}_samples_*.parquet"
                    )
                    fixed_strike._load_historical_frames.clear()
                    options.load_historical_sample_window.clear()

                    def corrected_query(
                        *query_args: object,
                        _timings: Timings = timings,
                        _raw_query: Callable[..., object] = raw_query,
                        **query_kwargs: object,
                    ) -> object:
                        return _timings.measure(
                            "DuckDB corrected-glob query",
                            _raw_query,
                            *query_args,
                            **query_kwargs,
                        )

                    with ExitStack() as retry_stack:
                        retry_stack.enter_context(
                            patch.object(
                                reader, "ensure_parquet_range", return_value=corrected_glob
                            )
                        )
                        retry_stack.enter_context(
                            patch.object(
                                reader.options_query, "load_sample_window", corrected_query
                            )
                        )
                        frames, sample_times = fixed_strike._load_historical_frames(
                            symbol, args.lookback_days, args.interval_minutes
                        )
                load_seconds = time.perf_counter() - started
                if frames:
                    stats = timings.measure(
                        "build z-score buckets",
                        fixed_strike.build_bucket_stats,
                        frames,
                        sample_times,
                    )
                else:
                    stats = None

            after_count, after_bytes = cache_stats(reader._cfg.cache_dir, symbol)
            rows = sum(len(frame) for frame in frames)
            frame_bytes = sum(int(frame.memory_usage(deep=True).sum()) for frame in frames)
            print(
                f"  frames={len(frames)} rows={rows:,} dataframe={format_bytes(frame_bytes)} "
                f"bucket-entries={len(stats) if stats is not None else 0} "
                f"load={load_seconds:.2f}s "
                f"cached-after={after_count} files/{format_bytes(after_bytes)} "
                f"added={format_bytes(after_bytes - before_bytes)}"
            )
            if sample_times:
                print(f"  sampled-at={min(sample_times)} through {max(sample_times)}")
                if max(sample_times).date() > as_of:
                    print("  WARNING: query included cached samples after the as-of date")
            timings.print()
            successful += 1
        except Exception as exc:
            print(f"  ERROR {type(exc).__name__}: {exc}")

    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
