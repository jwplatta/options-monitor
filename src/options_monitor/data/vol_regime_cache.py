"""Persistent, source-validated historical observations for the Vol Regime chart."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from datetime import date
from pathlib import Path

# Increment when the expiry selection, snapshot sampling, or IV/RR calculation changes.
_CALC_VERSION = 1

Observation = tuple[str, float | None, float | None]


def cache_path() -> Path:
    override = os.environ.get("VOL_REGIME_CACHE_PATH")
    if override:
        return Path(override).expanduser()
    root = Path(
        os.environ.get("OPTIONS_MONITOR_CACHE_DIR") or "~/.cache/options-monitor"
    ).expanduser()
    return root / "vol_regime.sqlite3"


def _source_stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


class VolRegimeObservationStore:
    """One SQLite connection per chart calculation; no age-based eviction."""

    def __init__(self, path: Path | None = None) -> None:
        db_path = path or cache_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_days (
                symbol TEXT NOT NULL,
                sample_date TEXT NOT NULL,
                target_dte INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                source_size INTEGER NOT NULL,
                source_mtime_ns INTEGER NOT NULL,
                calc_version INTEGER NOT NULL,
                PRIMARY KEY (symbol, sample_date, target_dte)
            );
            CREATE TABLE IF NOT EXISTS observations (
                symbol TEXT NOT NULL,
                sample_date TEXT NOT NULL,
                target_dte INTEGER NOT NULL,
                sampled_at TEXT NOT NULL,
                atm_iv REAL,
                risk_reversal REAL,
                PRIMARY KEY (symbol, sample_date, target_dte, sampled_at)
            );
            """
        )

    def __enter__(self) -> VolRegimeObservationStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self._conn.close()

    def get(self, symbol: str, sample_date: date, target_dte: int) -> list[Observation] | None:
        key = (symbol, sample_date.isoformat(), target_dte)
        meta = self._conn.execute(
            """SELECT source_path, source_size, source_mtime_ns, calc_version
               FROM history_days WHERE symbol=? AND sample_date=? AND target_dte=?""",
            key,
        ).fetchone()
        if meta is None or meta[3] != _CALC_VERSION:
            return None
        if _source_stamp(Path(meta[0])) != (meta[1], meta[2]):
            return None
        return self._conn.execute(
            """SELECT sampled_at, atm_iv, risk_reversal FROM observations
               WHERE symbol=? AND sample_date=? AND target_dte=? ORDER BY sampled_at""",
            key,
        ).fetchall()

    def put(
        self,
        symbol: str,
        sample_date: date,
        target_dte: int,
        source_path: Path,
        observations: Sequence[Observation],
    ) -> None:
        stamp = _source_stamp(source_path)
        if stamp is None:
            return
        key = (symbol, sample_date.isoformat(), target_dte)
        with self._conn:
            self._conn.execute(
                "DELETE FROM observations WHERE symbol=? AND sample_date=? AND target_dte=?", key
            )
            self._conn.executemany(
                """INSERT INTO observations
                   (symbol, sample_date, target_dte, sampled_at, atm_iv, risk_reversal)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(*key, *row) for row in observations],
            )
            self._conn.execute(
                """INSERT INTO history_days VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, sample_date, target_dte) DO UPDATE SET
                     source_path=excluded.source_path,
                     source_size=excluded.source_size,
                     source_mtime_ns=excluded.source_mtime_ns,
                     calc_version=excluded.calc_version""",
                (*key, str(source_path), *stamp, _CALC_VERSION),
            )
