"""Shared SQLite cache database and lightweight schema migrations."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 2
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
    2: (
        "DROP TABLE observations",
        "DROP TABLE history_days",
        """CREATE TABLE cache_namespaces (
            namespace_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL,
            historical_bucket TEXT NOT NULL, provider TEXT NOT NULL,
            UNIQUE(endpoint, historical_bucket, provider))""",
        """CREATE TABLE cache_sources (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL, sample_date TEXT NOT NULL,
            uri TEXT NOT NULL, revision TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            checked_at TEXT NOT NULL, PRIMARY KEY(namespace_id, root, sample_date))""",
        """CREATE TABLE cache_job_state (
            job_id TEXT NOT NULL, namespace_id TEXT NOT NULL, root TEXT NOT NULL,
            params_json TEXT NOT NULL, calc_version INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','ready','failed')),
            requested_at TEXT, started_at TEXT, completed_at TEXT, last_accessed_at TEXT,
            priority INTEGER NOT NULL DEFAULT 1,
            next_attempt_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
            PRIMARY KEY(job_id, namespace_id, root, params_json))""",
        "CREATE INDEX cache_jobs_due ON cache_job_state(status, next_attempt_at)",
        """CREATE TABLE cache_warmup_targets (
            job_id TEXT NOT NULL, namespace_id TEXT NOT NULL, root TEXT NOT NULL,
            params_json TEXT NOT NULL, enabled INTEGER NOT NULL, position INTEGER NOT NULL,
            PRIMARY KEY(job_id, namespace_id, root, params_json))""",
        """CREATE TABLE cache_metadata (
            namespace_id TEXT NOT NULL, metadata_key TEXT NOT NULL,
            payload_json TEXT NOT NULL, refreshed_at TEXT NOT NULL, last_error TEXT,
            PRIMARY KEY(namespace_id, metadata_key))""",
        """CREATE TABLE cache_settings (
            setting_key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE cache_generations (
            namespace_id TEXT NOT NULL, job_id TEXT NOT NULL, root TEXT NOT NULL,
            generation INTEGER NOT NULL, PRIMARY KEY(namespace_id, job_id, root))""",
        """CREATE TABLE vol_regime_days (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL, sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL, calc_version INTEGER NOT NULL,
            source_revision TEXT NOT NULL, selected_expiry TEXT, computed_at TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('ready','no_valid_observations')),
            PRIMARY KEY(namespace_id, root, sample_date, target_dte))""",
        """CREATE TABLE vol_regime_observations (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL, sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL, sampled_at TEXT NOT NULL, atm_iv REAL,
            risk_reversal REAL,
            PRIMARY KEY(namespace_id, root, sample_date, target_dte, sampled_at),
            FOREIGN KEY(namespace_id, root, sample_date, target_dte)
                REFERENCES vol_regime_days(namespace_id, root, sample_date, target_dte)
                ON DELETE CASCADE)""",
        "CREATE INDEX regime_range ON vol_regime_observations"
        "(namespace_id, root, target_dte, sample_date)",
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
    if int(conn.execute("PRAGMA user_version").fetchone()[0]) == _SCHEMA_VERSION:
        return
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
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        _migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn
