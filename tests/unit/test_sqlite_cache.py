"""Central cache database initialization and schema versioning."""

import sqlite3
from pathlib import Path

import pytest

from options_monitor.data.sqlite_cache import connect_cache


def test_first_connection_creates_all_cache_tables_and_sets_version(tmp_path: Path) -> None:
    path = tmp_path / "cache" / "options_monitor_cache.sqlite3"

    conn = connect_cache(path)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"bucket_stats", "history_days", "observations", "skew_curves"} <= tables
        assert conn.execute("PRAGMA user_version").fetchone() == (1,)
    finally:
        conn.close()


def test_newer_schema_version_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="newer than supported"):
        connect_cache(path)
