"""Shared SQLite cache database and lightweight schema migrations."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 1
_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """CREATE TABLE bucket_stats (
            symbol TEXT NOT NULL,
            lookback_days INTEGER NOT NULL,
            interval_minutes INTEGER NOT NULL,
            calc_version INTEGER NOT NULL,
            source_stamps_json TEXT NOT NULL,
            stats_json TEXT NOT NULL,
            sample_days INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (symbol, lookback_days, interval_minutes)
        )""",
        """CREATE TABLE history_days (
            symbol TEXT NOT NULL,
            sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            calc_version INTEGER NOT NULL,
            PRIMARY KEY (symbol, sample_date, target_dte)
        )""",
        """CREATE TABLE observations (
            symbol TEXT NOT NULL,
            sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL,
            sampled_at TEXT NOT NULL,
            atm_iv REAL,
            risk_reversal REAL,
            PRIMARY KEY (symbol, sample_date, target_dte, sampled_at)
        )""",
        """CREATE TABLE skew_curves (
            symbol TEXT NOT NULL,
            sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            calc_version INTEGER NOT NULL,
            points_json TEXT NOT NULL,
            PRIMARY KEY (symbol, sample_date, target_dte)
        )""",
    ),
}


def cache_path() -> Path:
    """Return the shared Options Monitor cache database path."""
    root = Path(
        os.environ.get("OPTIONS_MONITOR_CACHE_DIR") or "~/.cache/options-monitor"
    ).expanduser()
    return root / "options_monitor_cache.sqlite3"


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending cache schema migrations in one central place."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > _SCHEMA_VERSION:
            raise RuntimeError(
                f"Cache database schema {version} is newer than supported {_SCHEMA_VERSION}"
            )
        while version < _SCHEMA_VERSION:
            target_version = version + 1
            for statement in _MIGRATIONS[target_version]:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {target_version}")
            version = target_version
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect_cache(path: Path | None = None) -> sqlite3.Connection:
    """Open the shared cache database, applying its schema migrations first."""
    db_path = path or cache_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        _migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn
