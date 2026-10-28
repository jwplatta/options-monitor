"""Vol Regime's registration of the reusable dashboard cache job contract."""

from __future__ import annotations

import atexit
import json
import threading
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from tractatus.calc.vol import compute_risk_reversal
from tractatus.reader import CacheReader, ReaderConfig

from options_monitor.calc.vol_regime import compute_atm_iv
from options_monitor.data.cache_jobs import CacheJobs, JobDefinition, market_today, now_utc
from options_monitor.data.vol_regime_cache import CALC_VERSION, VolRegimeObservationStore

_runtime: CacheJobs | None = None
_runtime_lock = threading.Lock()


def validate(params: dict[str, Any]) -> dict[str, Any]:
    dte = params.get("target_dte")
    if set(params) != {"target_dte"} or type(dte) is not int or dte not in (5, 15, 30, 45):
        raise ValueError("target_dte must be one of 5, 15, 30, 45")
    return {"target_dte": dte}


def register_vol_regime(jobs: CacheJobs) -> None:
    def cleanup(cutoff: date) -> None:
        with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
            store.cleanup(cutoff)
        distributions.cache_clear()

    def compute(root: str, params: dict[str, Any]) -> None:
        reader = CacheReader()
        cutoff = market_today() - timedelta(days=jobs.retention("vol_regime"))
        sources = reader.list_option_sources(root, cutoff, market_today() - timedelta(days=1))
        with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
            revisions = store.revisions(root, params["target_dte"])
            with reader.query_connection() as conn:
                for source in sources:
                    if revisions.get(source.sample_date.isoformat()) == source.revision:
                        continue
                    frame = reader.option_daily_snapshots(source, params["target_dte"], conn)
                    observations = []
                    for timestamp, chain in frame.groupby("sampled_at", sort=True):
                        spots = pd.to_numeric(chain.underlying_price, errors="coerce").dropna()
                        iv = (
                            compute_atm_iv(chain, float(spots.iloc[0])) if not spots.empty else None
                        )
                        rr = compute_risk_reversal(chain)
                        observations.append((str(timestamp), iv, rr.rr if rr is not None else None))
                    expiry = str(frame.expiration_date.iloc[0])[:10] if not frame.empty else None
                    store.put(
                        root,
                        source.sample_date,
                        params["target_dte"],
                        source.revision,
                        observations,
                        expiry,
                    )
        # Only a completely successful inventory/compute publishes the new date list.
        with jobs.connection() as db:
            db.execute(
                "DELETE FROM cache_sources WHERE namespace_id=? AND root=?", (jobs.namespace, root)
            )
            db.executemany(
                "INSERT INTO cache_sources VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        jobs.namespace,
                        root,
                        s.sample_date.isoformat(),
                        s.uri,
                        s.revision,
                        s.size_bytes,
                        now_utc(),
                    )
                    for s in sources
                ],
            )
            days = {source.sample_date.isoformat() for source in sources}
            obsolete = db.execute(
                "SELECT DISTINCT sample_date FROM vol_regime_days WHERE namespace_id=? AND root=?",
                (jobs.namespace, root),
            ).fetchall()
            removed = [day for (day,) in obsolete if day not in days]
            for day in removed:
                db.execute(
                    "DELETE FROM vol_regime_days WHERE namespace_id=? AND root=? AND sample_date=?",
                    (jobs.namespace, root, day),
                )
            if removed:
                db.execute(
                    "INSERT INTO cache_generations VALUES (?,'vol_regime',?,1) "
                    "ON CONFLICT(namespace_id,job_id,root) DO UPDATE SET "
                    "generation=generation+1",
                    (jobs.namespace, root),
                )
        distributions.cache_clear()

    jobs.register(
        JobDefinition("vol_regime", CALC_VERSION, {"target_dte": 30}, validate, compute, cleanup)
    )


def runtime() -> CacheJobs:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            cfg = ReaderConfig.load()
            _runtime = CacheJobs(cfg.minio_endpoint, cfg.minio_lakehouse_bucket)
            register_vol_regime(_runtime)
            register_roots(_runtime)
            _runtime.request("option_roots", "", {})
            atexit.register(_runtime.close)
            _runtime.start()
        return _runtime


@lru_cache(maxsize=128)
def distributions(
    namespace: str,
    path: str | None,
    root: str,
    target_dte: int,
    after: date,
    before: date,
    generation: int,
) -> tuple[tuple[float, ...], tuple[float, ...], date | None]:
    from pathlib import Path

    with VolRegimeObservationStore(Path(path) if path else None, namespace) as store:
        ivs, rrs, through = store.get_range(root, target_dte, after, before)
    return tuple(sorted(ivs)), tuple(sorted(rrs)), through


def history(
    root: str, target_dte: int, after: date, before: date
) -> tuple[list[float], list[float], date | None]:
    jobs = runtime()
    jobs.request("vol_regime", root, {"target_dte": target_dte})
    after = max(after, market_today() - timedelta(days=jobs.retention("vol_regime")))
    with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
        generation = store.generation(root)
    ivs, rrs, through = distributions(
        jobs.namespace,
        str(jobs.path) if jobs.path else None,
        root,
        target_dte,
        after,
        before,
        generation,
    )
    return list(ivs), list(rrs), through


def available_dates(root: str, after: date, before: date) -> list[date]:
    jobs = runtime()
    with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
        return store.dates(root, after, before)


def register_roots(jobs: CacheJobs) -> None:
    def compute(_root: str, _params: dict[str, Any]) -> None:
        roots = CacheReader().list_roots()
        with jobs.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache_metadata VALUES (?,?,?,?,NULL)",
                (jobs.namespace, "option_roots", json.dumps(roots), now_utc()),
            )

    jobs.register(
        JobDefinition(
            "option_roots",
            1,
            {},
            lambda p: {},
            compute,
            lambda cutoff: None,
            refresh_seconds=300,
            default_roots=(),
        )
    )


def cached_roots() -> tuple[list[str], bool]:
    """Persist metadata across app restarts; remote refresh uses the shared worker."""
    jobs = runtime()
    jobs.request("option_roots", "", {})
    with jobs.connection() as db:
        row = db.execute(
            "SELECT payload_json FROM cache_metadata WHERE namespace_id=? AND metadata_key=?",
            (jobs.namespace, "option_roots"),
        ).fetchone()
    return (json.loads(row[0]), True) if row else (["SPXW"], False)
