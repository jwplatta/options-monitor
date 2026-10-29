"""Time discovery, daily selection, IV/RR calculation, and cache writes separately.

Uses the current worker's calculation sequence and public CacheReader methods.
Writes only to --cache-dir. Source object bytes do not measure network traffic.
No server/OS caches are cleared; repeated runs can benefit from those caches.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import pandas as pd
from tractatus.reader import CacheReader

from options_monitor.calc.risk_reversal import compute_risk_reversal
from options_monitor.calc.vol_regime import compute_atm_iv
from options_monitor.data.cache_jobs import market_today
from options_monitor.data.vol_regime_cache import VolRegimeObservationStore


def measure(root: str, days: int, target_dte: int, path: Path) -> dict[str, object]:
    started = perf_counter()
    reader = CacheReader()
    reader_setup = perf_counter() - started
    stage = perf_counter()
    sources = reader.list_option_sources(
        root, market_today() - timedelta(days=days), market_today() - timedelta(days=1)
    )
    discovery = perf_counter() - stage
    print(json.dumps(dict(event="discovered", root=root, days=len(sources))), flush=True)
    selection = calculation = persistence = 0.0
    snapshots = selected_rows = 0
    day_timings = []
    stage = perf_counter()
    with VolRegimeObservationStore(path) as store:
        store_setup = perf_counter() - stage
        stage = perf_counter()
        with reader.query_connection() as conn:
            query_setup = perf_counter() - stage
            for source in sources:
                stage = perf_counter()
                frame = reader.option_daily_snapshots(source, target_dte, conn)
                selected = perf_counter() - stage
                selection += selected
                selected_rows += len(frame)
                stage = perf_counter()
                observations = []
                for timestamp, chain in frame.groupby("sampled_at", sort=True):
                    spots = pd.to_numeric(chain.underlying_price, errors="coerce").dropna()
                    iv = compute_atm_iv(chain, float(spots.iloc[0])) if not spots.empty else None
                    rr = compute_risk_reversal(chain)
                    observations.append((str(timestamp), iv, rr.rr if rr is not None else None))
                expiry = str(frame.expiration_date.iloc[0])[:10] if not frame.empty else None
                calculated = perf_counter() - stage
                calculation += calculated
                snapshots += len(observations)
                stage = perf_counter()
                store.put(
                    root, source.sample_date, target_dte, source.revision, observations, expiry
                )
                persisted = perf_counter() - stage
                persistence += persisted
                day_timings.append(
                    dict(
                        sample_date=source.sample_date.isoformat(),
                        selected_rows=len(frame),
                        observations=len(observations),
                        selection_s=selected,
                        calculation_s=calculated,
                        sqlite_write_s=persisted,
                    )
                )
    total = perf_counter() - started
    return dict(
        root=root,
        calendar_days=days,
        historical_days=len(sources),
        target_dte=target_dte,
        observations=snapshots,
        selected_rows=selected_rows,
        source_object_bytes=sum(s.size_bytes for s in sources),
        history_through=str(sources[-1].sample_date) if sources else None,
        total_s=total,
        reader_setup_s=reader_setup,
        discovery_s=discovery,
        sqlite_setup_s=store_setup,
        query_setup_s=query_setup,
        selection_s=selection,
        calculation_s=calculation,
        sqlite_write_s=persistence,
        calculation_share_of_selection_and_calc_pct=(
            100 * calculation / (selection + calculation) if selection + calculation else 0
        ),
        per_day=day_timings,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["SPXW", "TSLA"])
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--target-dte", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.days, args.repeats) < 1 or args.target_dte < 0:
        parser.error("days/repeats must be positive and target DTE nonnegative")
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for repeat in range(1, args.repeats + 1):
        for root in args.symbols:
            # Each measurement starts without derived metrics; refuse to reuse old files.
            path = args.cache_dir / f"{root}-{repeat}.sqlite3"
            if path.exists():
                raise FileExistsError(f"Use a fresh profile cache directory: {path}")
            result = measure(root, args.days, args.target_dte, path)
            result["repeat"] = repeat
            results.append(result)
            print(json.dumps({k: v for k, v in result.items() if k != "per_day"}), flush=True)
            args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
