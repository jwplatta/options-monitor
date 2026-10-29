"""Compare per-symbol discovery with persistent multi-root inventory reuse."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from tractatus.reader import CacheReader

from options_monitor.data.cache_jobs import CacheJobs, market_today
from options_monitor.data.source_inventory import SourceInventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM", "INTC", "MRVL"])
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = args.cache_dir / "inventory.sqlite3"
    if path.exists():
        raise FileExistsError(f"Use a fresh benchmark cache directory: {path}")
    after, before = market_today() - timedelta(days=args.days), market_today() - timedelta(days=1)
    reader = CacheReader()
    endpoint, bucket = reader.source_namespace
    jobs = CacheJobs(endpoint, bucket, path=path)
    baseline = {}
    timings = {}
    for root in args.symbols:
        start = perf_counter()
        baseline[root] = reader.list_option_sources(root, after, before)
        timings[root] = perf_counter() - start
        print(
            json.dumps(
                dict(
                    event="baseline", root=root, seconds=timings[root], sources=len(baseline[root])
                )
            ),
            flush=True,
        )
    inventory = SourceInventory(jobs)
    start = perf_counter()
    shared = inventory.get(reader, args.symbols, after, before)
    shared_s = perf_counter() - start
    assert shared == baseline, "Source inventories differ; do not compare unequal work"
    start = perf_counter()
    for root in args.symbols:
        reused = inventory.get(reader, [root], after, before)
        assert reused[root] == baseline[root]
    reuse_s = perf_counter() - start
    result = dict(
        symbols=args.symbols,
        calendar_days=args.days,
        sources={root: len(sources) for root, sources in baseline.items()},
        baseline_per_root_s=timings,
        baseline_total_s=sum(timings.values()),
        shared_initial_s=shared_s,
        shared_reuse_all_roots_s=reuse_s,
        initial_speedup=sum(timings.values()) / shared_s,
        equal_sources=True,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
