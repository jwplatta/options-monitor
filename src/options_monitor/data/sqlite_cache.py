"""Current definitions for the disposable dashboard cache; no schema migrations."""

from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from threading import Lock

from options_monitor.data.option_root_config import configured_option_roots, seed_option_roots

_INITIALIZE_LOCK = Lock()

# Edit these definitions directly. A differing cache schema is rebuilt on open.
_SCHEMA: tuple[str, ...] = (
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
    """CREATE TABLE cache_namespaces (
            namespace_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL,
            historical_bucket TEXT NOT NULL, provider TEXT NOT NULL,
            UNIQUE(endpoint, historical_bucket, provider))""",
    """CREATE TABLE cache_sources (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL, sample_date TEXT NOT NULL,
            uri TEXT NOT NULL, revision TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            checked_at TEXT NOT NULL, PRIMARY KEY(namespace_id, root, sample_date))""",
    """CREATE TABLE cache_source_scans (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL,
            after_date TEXT NOT NULL, before_date TEXT NOT NULL,
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY(namespace_id, root))""",
    """CREATE TABLE cache_job_state (
            job_id TEXT NOT NULL, namespace_id TEXT NOT NULL, root TEXT NOT NULL,
            params_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','ready','failed')),
            requested_at TEXT, started_at TEXT, completed_at TEXT, last_accessed_at TEXT,
            priority INTEGER NOT NULL DEFAULT 1,
            next_attempt_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
            PRIMARY KEY(job_id, namespace_id, root, params_json))""",
    """CREATE INDEX cache_jobs_due ON cache_job_state(status, next_attempt_at)""",
    """CREATE TABLE cache_warmup_targets (
            job_id TEXT NOT NULL, namespace_id TEXT NOT NULL, root TEXT NOT NULL,
            params_json TEXT NOT NULL, enabled INTEGER NOT NULL, position INTEGER NOT NULL,
            PRIMARY KEY(job_id, namespace_id, root, params_json))""",
    """CREATE TABLE option_roots (
            option_root TEXT NOT NULL, underlying TEXT NOT NULL,
            namespace_id TEXT NOT NULL, refreshed_at TEXT NOT NULL, last_error TEXT,
            metadata_json TEXT NOT NULL,
            PRIMARY KEY(namespace_id, option_root))""",
    """CREATE INDEX option_roots_root ON option_roots(option_root)""",
    """CREATE TABLE cache_settings (
            setting_key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE cache_generations (
            namespace_id TEXT NOT NULL, job_id TEXT NOT NULL, root TEXT NOT NULL,
            generation INTEGER NOT NULL, PRIMARY KEY(namespace_id, job_id, root))""",
    """CREATE TABLE vol_regime_days (
            namespace_id TEXT NOT NULL, root TEXT NOT NULL, sample_date TEXT NOT NULL,
            target_dte INTEGER NOT NULL,
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
    """CREATE INDEX regime_range ON vol_regime_observations
        (namespace_id, root, target_dte, sample_date)""",
)


def cache_path() -> Path:
    """Return the shared Options Monitor cache database path."""
    root = Path(
        os.environ.get("OPTIONS_MONITOR_CACHE_DIR") or "~/.cache/options-monitor"
    ).expanduser()
    return root / "options_monitor_cache.sqlite3"


def _schema(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {
        (kind, name): " ".join(sql.split())
        for kind, name, sql in conn.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        )
    }


@lru_cache(maxsize=1)
def _expected_schema() -> dict[tuple[str, str], str]:
    conn = sqlite3.connect(":memory:")
    try:
        for statement in _SCHEMA:
            conn.execute(statement)
        return _schema(conn)
    finally:
        conn.close()


def _initialize(conn: sqlite3.Connection) -> None:
    """Recreate incompatible caches atomically; retain matching caches on reopen."""
    if _schema(conn) == _expected_schema():
        return
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Another connection may have initialized it while we waited for the lock.
        if _schema(conn) != _expected_schema():
            objects = conn.execute(
                "SELECT type,name FROM sqlite_master WHERE type IN ('view','table') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY type DESC"
            ).fetchall()
            for kind, name in objects:
                quoted = name.replace('"', '""')
                conn.execute(f'DROP {kind.upper()} "{quoted}"')
            for statement in _SCHEMA:
                conn.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def connect_cache(path: Path | None = None) -> sqlite3.Connection:
    """Open a cache using the current schema, rebuilding incompatible contents."""
    configured_option_roots()  # Validate config before touching an existing cache.
    db_path = path or cache_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLite journal-mode setup can fail immediately if sibling threads initialize
    # a new file simultaneously, before its normal busy handling takes effect.
    with _INITIALIZE_LOCK:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            _initialize(conn)
            with conn:
                seed_option_roots(conn)
        except Exception:
            conn.close()
            raise
    return conn
