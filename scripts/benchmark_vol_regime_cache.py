"""Measure historical Vol Regime preparation against MinIO with an isolated cache.

Run in the dev container with OPTIONS_MONITOR_CACHE_DIR pointing to a disposable
benchmark directory. Reported source bytes are object sizes, not wire traffic.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from time import perf_counter

from tractatus.reader import CacheReader, ReaderConfig

from options_monitor.data.cache_jobs import CacheJobs, market_today
from options_monitor.data.vol_regime_cache import VolRegimeObservationStore
from options_monitor.data.vol_regime_jobs import distributions, register_vol_regime


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["SPXW", "TSLA"])
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    cfg = ReaderConfig.load()
    jobs = CacheJobs(cfg.minio_endpoint, cfg.minio_lakehouse_bucket)
    register_vol_regime(jobs)
    jobs.set_setting("vol_regime:retention_days", args.days)
    after = market_today() - timedelta(days=args.days)
    for root in args.symbols:
        start = perf_counter()
        sources = CacheReader().list_option_sources(root, after, market_today() - timedelta(days=1))
        discovery = perf_counter() - start
        start = perf_counter()
        jobs.definitions["vol_regime"].compute(root, {"target_dte": 30})
        cold = perf_counter() - start
        with VolRegimeObservationStore(namespace=jobs.namespace) as store:
            generation = store.generation(root)
            start = perf_counter()
            ivs, rrs, through = store.get_range(root, 30, after, market_today())
            sqlite_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        for _ in range(100):
            distributions(jobs.namespace, None, root, 30, after, market_today(), generation)
        warm_ms = (perf_counter() - start) * 10
        start = perf_counter()
        jobs.definitions["vol_regime"].compute(root, {"target_dte": 30})
        unchanged = perf_counter() - start
        print(
            json.dumps(
                dict(
                    root=root,
                    historical_days=len(sources),
                    discovery_seconds=discovery,
                    cold_seconds=cold,
                    unchanged_refresh_seconds=unchanged,
                    sqlite_range_ms=sqlite_ms,
                    warm_distribution_ms=warm_ms,
                    iv_count=len(ivs),
                    rr_count=len(rrs),
                    history_through=str(through),
                    source_object_bytes=sum(s.size_bytes for s in sources),
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
