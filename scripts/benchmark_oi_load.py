#!/usr/bin/env python3
"""Measure Open Interest historical and current-chain loading stages.

Run from the application environment, for example:
    python scripts/benchmark_oi_load.py --symbol SPXW --lookback-days 30

The script resolves the requested historical Parquet range through DataReader, so
the first run may download files. Repeated rounds help distinguish cold file
resolution from warm DuckDB/query and Python calculation costs.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("DUCKDB_OPTIONS_PATH", f"/tmp/duckdb_oi_benchmark_{os.getpid()}.db")

import pandas as pd
from tractatus.calc.oi import build_oi_matrix
from tractatus.calc.oi_zscore import build_oi_bucket_stats, compute_oi_zscore_matrix

from options_monitor.data.reader import get_reader

_CHICAGO = ZoneInfo("America/Chicago")
_HISTORICAL_COLUMNS = [
    "sampled_at",
    "expiration_date",
    "strike",
    "contract_type",
    "open_interest",
    "underlying_price",
]


def _measure(fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - started


def _group_frames(df: pd.DataFrame) -> tuple[list[pd.DataFrame], list[datetime]]:
    if df.empty:
        return [], []
    work = df.copy()
    work["sampled_at"] = pd.to_datetime(work["sampled_at"], utc=True)
    frames: list[pd.DataFrame] = []
    sample_times: list[datetime] = []
    for sampled_at, group in work.groupby("sampled_at", sort=True):
        frames.append(group.reset_index(drop=True))
        sample_times.append(pd.Timestamp(sampled_at).to_pydatetime())
    return frames, sample_times


def _report(label: str, seconds: float) -> None:
    print(f"  {label:<50} {seconds:8.3f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPXW")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--days-out", type=int, default=30)
    parser.add_argument("--contract-type", choices=["CALL", "PUT", "OTM"], default="CALL")
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()

    reader = get_reader()
    today = date.today()
    sample_start = today - timedelta(days=args.lookback_days)
    end_expiry = today + timedelta(days=args.days_out)
    print(
        f"OI benchmark: symbol={args.symbol} lookback={args.lookback_days}d "
        f"interval={args.interval_minutes}m days_out={args.days_out} "
        f"contract={args.contract_type} rounds={args.rounds}"
    )

    latest_stats: pd.DataFrame | None = None
    for round_number in range(1, args.rounds + 1):
        print(f"\nHistorical round {round_number}")
        paths, elapsed = _measure(reader.ensure_parquet_files, args.symbol, sample_start, today)
        _report(f"resolve/cache {len(paths)} parquet files", elapsed)
        if not paths:
            print("No historical Parquet files resolved; stopping.")
            return

        full_df, full_query = _measure(
            reader.options_query.load_sample_window,
            paths,
            sample_start,
            args.interval_minutes,
        )
        _report(f"full-column DuckDB query ({len(full_df):,} rows)", full_query)
        print(
            f"  {'full DataFrame memory':<50} {full_df.memory_usage(deep=True).sum() / 1e6:8.1f} MB"
        )

        full_grouped, full_group_time = _measure(_group_frames, full_df)
        full_frames, full_times = full_grouped
        _report(f"group full rows ({len(full_frames)} samples)", full_group_time)
        full_stats, full_stats_time = _measure(build_oi_bucket_stats, full_frames, full_times)
        _report(f"build full-column bucket stats ({len(full_stats)} buckets)", full_stats_time)

        narrow_df, narrow_query = _measure(
            reader.options_query.load_sample_window,
            paths,
            sample_start,
            args.interval_minutes,
            columns=_HISTORICAL_COLUMNS,
        )
        _report(f"projected DuckDB query ({len(narrow_df):,} rows)", narrow_query)
        print(
            f"  {'projected DataFrame memory':<50} "
            f"{narrow_df.memory_usage(deep=True).sum() / 1e6:8.1f} MB"
        )

        narrow_grouped, narrow_group_time = _measure(_group_frames, narrow_df)
        narrow_frames, narrow_times = narrow_grouped
        _report(f"group projected rows ({len(narrow_frames)} samples)", narrow_group_time)
        narrow_stats, narrow_stats_time = _measure(
            build_oi_bucket_stats, narrow_frames, narrow_times
        )
        _report(f"build projected bucket stats ({len(narrow_stats)} buckets)", narrow_stats_time)
        try:
            pd.testing.assert_frame_equal(
                full_stats,
                narrow_stats,
                check_exact=False,
                rtol=1e-12,
                atol=1e-9,
            )
        except AssertionError as exc:
            print("  Full vs projected bucket-stat differences:")
            print(full_stats.compare(narrow_stats).head(10).to_string())
            raise RuntimeError("Projected OI columns changed bucket statistics") from exc
        print("  Projected bucket stats match full-column results within numeric tolerance")
        latest_stats = narrow_stats

    print("\nCurrent chain and matrix stages")
    snapshots, discovery_time = _measure(reader.latest_snapshots, args.symbol, today, end_expiry)
    _report(f"discover {len(snapshots)} current expiries", discovery_time)
    loaded: dict[date, pd.DataFrame] = {}
    current_load_time = 0.0
    for expiry, uri in snapshots.items():
        snap, elapsed = _measure(reader.load_intraday_snapshot, uri)
        loaded[expiry] = snap
        current_load_time += elapsed
    _report(f"load {len(loaded)} current chains", current_load_time)

    spot = 0.0
    if loaded:
        values = pd.to_numeric(
            loaded[next(iter(loaded))]["underlying_price"], errors="coerce"
        ).dropna()
        if not values.empty:
            spot = float(values.iloc[0])

    oi_matrix, matrix_time = _measure(build_oi_matrix, loaded, args.contract_type, spot)
    _report(f"build current OI matrix ({oi_matrix.shape})", matrix_time)

    if latest_stats is not None and not latest_stats.empty:
        z_matrix, zscore_time = _measure(
            compute_oi_zscore_matrix,
            loaded,
            latest_stats,
            spot,
            args.contract_type,
            datetime.now(_CHICAGO),
        )
        _report(f"compute OI z-score matrix ({z_matrix.shape})", zscore_time)


if __name__ == "__main__":
    main()
