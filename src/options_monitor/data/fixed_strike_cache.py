"""Persistent source-validated bucket statistics for Fixed Strike Vol."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

_CALC_VERSION = 1


def cache_path() -> Path:
    root = Path(
        os.environ.get("OPTIONS_MONITOR_CACHE_DIR") or "~/.cache/options-monitor"
    ).expanduser()
    return root / "fixed_strike.sqlite3"


def _source_stamps(paths: list[Path]) -> list[tuple[str, int, int]] | None:
    stamps: list[tuple[str, int, int]] = []
    for path in sorted(paths):
        try:
            stat = path.stat()
        except OSError:
            return None
        stamps.append((str(path), stat.st_size, stat.st_mtime_ns))
    return stamps


def _serialize_stats(stats: pd.DataFrame) -> str:
    frame = stats.reset_index()
    frame = frame.astype(object).mask(pd.isna(frame), None)
    rows = frame.to_dict(orient="records")
    return json.dumps(rows)


def _deserialize_stats(payload: str) -> pd.DataFrame:
    rows = json.loads(payload)
    if not rows:
        return pd.DataFrame(columns=["iv_mean", "iv_std", "count"])
    frame = pd.DataFrame.from_records(rows)
    frame["iv_mean"] = pd.to_numeric(frame["iv_mean"], errors="coerce")
    frame["iv_std"] = pd.to_numeric(frame["iv_std"], errors="coerce")
    frame["count"] = pd.to_numeric(frame["count"], errors="coerce").astype("int64")
    return frame.set_index(["contract_type", "dte_bucket", "moneyness_bucket"])[
        ["iv_mean", "iv_std", "count"]
    ]


class FixedStrikeBucketStore:
    """Cache one bucket-stat result for a parameter set and exact Parquet sources."""

    def __init__(self, path: Path | None = None) -> None:
        db_path = path or cache_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS bucket_stats (
                symbol TEXT NOT NULL,
                lookback_days INTEGER NOT NULL,
                interval_minutes INTEGER NOT NULL,
                calc_version INTEGER NOT NULL,
                source_stamps_json TEXT NOT NULL,
                stats_json TEXT NOT NULL,
                sample_days INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (symbol, lookback_days, interval_minutes)
            )"""
        )
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(bucket_stats)").fetchall()
        }
        if "sample_days" not in columns:
            self._conn.execute(
                "ALTER TABLE bucket_stats ADD COLUMN sample_days INTEGER NOT NULL DEFAULT 0"
            )

    def __enter__(self) -> FixedStrikeBucketStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self._conn.close()

    def get(
        self,
        symbol: str,
        lookback_days: int,
        interval_minutes: int,
        source_paths: list[Path],
    ) -> tuple[pd.DataFrame, int] | None:
        stamps = _source_stamps(source_paths)
        if stamps is None:
            return None
        row = self._conn.execute(
            """SELECT calc_version, source_stamps_json, stats_json, sample_days FROM bucket_stats
               WHERE symbol=? AND lookback_days=? AND interval_minutes=?""",
            (symbol, lookback_days, interval_minutes),
        ).fetchone()
        if row is None or row[0] != _CALC_VERSION:
            return None
        if json.loads(row[1]) != [list(stamp) for stamp in stamps]:
            return None
        return _deserialize_stats(row[2]), int(row[3])

    def put(
        self,
        symbol: str,
        lookback_days: int,
        interval_minutes: int,
        source_paths: list[Path],
        stats: pd.DataFrame,
        sample_days: int,
    ) -> None:
        stamps = _source_stamps(source_paths)
        if stamps is None:
            return
        with self._conn:
            self._conn.execute(
                """INSERT INTO bucket_stats
                   (symbol, lookback_days, interval_minutes, calc_version,
                    source_stamps_json, stats_json, sample_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, lookback_days, interval_minutes) DO UPDATE SET
                     calc_version=excluded.calc_version,
                     source_stamps_json=excluded.source_stamps_json,
                     stats_json=excluded.stats_json,
                     sample_days=excluded.sample_days""",
                (
                    symbol,
                    lookback_days,
                    interval_minutes,
                    _CALC_VERSION,
                    json.dumps(stamps),
                    _serialize_stats(stats),
                    sample_days,
                ),
            )
