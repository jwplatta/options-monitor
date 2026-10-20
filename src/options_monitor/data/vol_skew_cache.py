"""Persistent daily 30-DTE skew curves, separate from Tractatus's file cache."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from options_monitor.data.sqlite_cache import connect_cache

_CALC_VERSION = 1


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


class SkewCurveStore:
    """One row per archived symbol/date/target DTE; rows never age out."""

    def __init__(self, path: Path | None = None) -> None:
        self._conn = connect_cache(path)

    def __enter__(self) -> SkewCurveStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self._conn.close()

    def get(
        self, symbol: str, sample_date: date, target_dte: int
    ) -> list[tuple[float, float]] | None:
        row = self._conn.execute(
            """SELECT source_path, source_size, source_mtime_ns, calc_version, points_json
               FROM skew_curves WHERE symbol=? AND sample_date=? AND target_dte=?""",
            (symbol, sample_date.isoformat(), target_dte),
        ).fetchone()
        if row is None or row[3] != _CALC_VERSION or _stamp(Path(row[0])) != (row[1], row[2]):
            return None
        return [(float(m), float(iv)) for m, iv in json.loads(row[4])]

    def put(
        self,
        symbol: str,
        sample_date: date,
        target_dte: int,
        source_path: Path,
        points: list[tuple[float, float]],
    ) -> None:
        stamp = _stamp(source_path)
        if stamp is None:
            return
        with self._conn:
            self._conn.execute(
                """INSERT INTO skew_curves VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, sample_date, target_dte) DO UPDATE SET
                     source_path=excluded.source_path,
                     source_size=excluded.source_size,
                     source_mtime_ns=excluded.source_mtime_ns,
                     calc_version=excluded.calc_version,
                     points_json=excluded.points_json""",
                (
                    symbol,
                    sample_date.isoformat(),
                    target_dte,
                    str(source_path),
                    *stamp,
                    _CALC_VERSION,
                    json.dumps(points),
                ),
            )
