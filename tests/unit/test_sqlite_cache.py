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
        assert {
            "bucket_stats",
            "vol_regime_days",
            "vol_regime_observations",
            "skew_curves",
        } <= tables
        assert conn.execute("PRAGMA user_version").fetchone() == (2,)
    finally:
        conn.close()


def test_newer_schema_version_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="newer than supported"):
        connect_cache(path)


def test_destructive_regime_migration_preserves_other_chart_tables(tmp_path: Path) -> None:
    from options_monitor.data.sqlite_cache import _MIGRATIONS

    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        for ddl in _MIGRATIONS[1]:
            conn.execute(ddl)
        conn.execute("PRAGMA user_version=1")
        conn.execute("INSERT INTO history_days VALUES ('SPY','2026-10-14',30,'old',1,1,1)")
        conn.execute("INSERT INTO skew_curves VALUES ('SPY','2026-10-14',30,'old',1,1,1,'[]')")
    conn = connect_cache(path)
    try:
        assert conn.execute("SELECT count(*) FROM vol_regime_days").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM skew_curves").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT * FROM history_days")
    finally:
        conn.close()
