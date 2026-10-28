"""Compact historical Vol Regime metrics, versioned by remote source revision."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from options_monitor.data.cache_jobs import now_utc
from options_monitor.data.sqlite_cache import connect_cache

CALC_VERSION = 2
Observation = tuple[str, float | None, float | None]


class VolRegimeObservationStore:
    """Bulk range reads and atomic daily replacement; never access source objects."""

    def __init__(self, path: Path | None = None, namespace: str = "default") -> None:
        self._conn = connect_cache(path)
        self.namespace = namespace

    def __enter__(self) -> VolRegimeObservationStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self._conn.close()

    def revisions(self, root: str, target_dte: int) -> dict[str, str]:
        return dict(
            self._conn.execute(
                "SELECT sample_date,source_revision FROM vol_regime_days WHERE namespace_id=? "
                "AND root=? AND target_dte=? AND calc_version=?",
                (self.namespace, root, target_dte, CALC_VERSION),
            ).fetchall()
        )

    def generation(self, root: str) -> int:
        row = self._conn.execute(
            "SELECT generation FROM cache_generations WHERE namespace_id=? "
            "AND job_id='vol_regime' AND root=?",
            (self.namespace, root),
        ).fetchone()
        return int(row[0]) if row else 0

    def _increment(self, root: str) -> None:
        self._conn.execute(
            "INSERT INTO cache_generations VALUES (?,'vol_regime',?,1) "
            "ON CONFLICT(namespace_id,job_id,root) DO UPDATE SET "
            "generation=generation+1",
            (self.namespace, root),
        )

    def get_range(
        self, root: str, target_dte: int, after: date, before: date
    ) -> tuple[list[float], list[float], date | None]:
        rows = self._conn.execute(
            "SELECT o.atm_iv,o.risk_reversal,o.sample_date FROM vol_regime_observations o "
            "JOIN vol_regime_days d USING(namespace_id,root,sample_date,target_dte) "
            "WHERE o.namespace_id=? AND o.root=? AND o.target_dte=? "
            "AND o.sample_date>=? AND o.sample_date<? AND d.calc_version=? "
            "ORDER BY o.sample_date,o.sampled_at",
            (self.namespace, root, target_dte, after.isoformat(), before.isoformat(), CALC_VERSION),
        ).fetchall()
        ivs = [float(r[0]) for r in rows if r[0] is not None and math.isfinite(r[0])]
        rrs = [float(r[1]) for r in rows if r[1] is not None and math.isfinite(r[1])]
        return ivs, rrs, date.fromisoformat(rows[-1][2]) if rows else None

    def dates(self, root: str, after: date, before: date) -> list[date]:
        return [
            date.fromisoformat(r[0])
            for r in self._conn.execute(
                "SELECT sample_date FROM cache_sources WHERE namespace_id=? AND root=? "
                "AND sample_date>=? AND sample_date<=? ORDER BY sample_date",
                (self.namespace, root, after.isoformat(), before.isoformat()),
            )
        ]

    def put(
        self,
        root: str,
        sample_date: date,
        target_dte: int,
        revision: str,
        observations: Sequence[Observation],
        expiry: str | None = None,
    ) -> None:
        key = (self.namespace, root, sample_date.isoformat(), target_dte)
        rows = [
            (
                ts,
                iv if iv is not None and math.isfinite(iv) else None,
                rr if rr is not None and math.isfinite(rr) else None,
            )
            for ts, iv, rr in observations
        ]
        with self._conn:
            self._conn.execute(
                "DELETE FROM vol_regime_days WHERE namespace_id=? AND root=? "
                "AND sample_date=? AND target_dte=?",
                key,
            )
            self._conn.execute(
                "INSERT INTO vol_regime_days VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    *key,
                    CALC_VERSION,
                    revision,
                    expiry,
                    now_utc(),
                    "ready" if rows else "no_valid_observations",
                ),
            )
            self._conn.executemany(
                "INSERT INTO vol_regime_observations VALUES (?,?,?,?,?,?,?)",
                [(*key, ts, iv, rr) for ts, iv, rr in rows],
            )
            self._increment(root)

    def cleanup(self, cutoff: date) -> None:
        with self._conn:
            roots = self._conn.execute(
                "SELECT DISTINCT root FROM vol_regime_days WHERE namespace_id=? AND sample_date<?",
                (self.namespace, cutoff.isoformat()),
            ).fetchall()
            self._conn.execute(
                "DELETE FROM vol_regime_days WHERE namespace_id=? AND sample_date<?",
                (self.namespace, cutoff.isoformat()),
            )
            self._conn.execute(
                "DELETE FROM cache_sources WHERE namespace_id=? AND sample_date<?",
                (self.namespace, cutoff.isoformat()),
            )
            for (root,) in roots:
                self._increment(root)
