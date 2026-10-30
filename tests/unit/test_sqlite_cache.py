"""Disposable cache creation, rebuilding, and reopen behavior."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from options_monitor.data.sqlite_cache import connect_cache


def test_current_schema_has_no_obsolete_tables(tmp_path: Path) -> None:
    conn = connect_cache(tmp_path / "cache.sqlite3")
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "bucket_stats",
            "skew_curves",
            "vol_regime_days",
            "vol_regime_observations",
        } <= tables
        assert not {"history_days", "observations"} & tables
        assert conn.execute("PRAGMA user_version").fetchone() == (0,)
    finally:
        conn.close()


def test_matching_schema_preserves_saved_settings_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    conn = connect_cache(path)
    with conn:
        conn.execute("INSERT INTO cache_settings VALUES ('warmup','[\"QQQ\"]','now')")
    conn.close()
    conn = connect_cache(path)
    try:
        assert conn.execute("SELECT value_json FROM cache_settings").fetchone()[0] == '["QQQ"]'
    finally:
        conn.close()


def test_incompatible_cache_is_rebuilt_without_versions(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE observations (old_column TEXT)")
        conn.execute("CREATE TABLE cache_settings (incompatible TEXT)")
    conn = connect_cache(path)
    try:
        assert conn.execute("SELECT count(*) FROM cache_settings").fetchone()[0] == 0
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name='observations'"
        ).fetchall()
        conn.execute("INSERT INTO cache_settings VALUES ('key','1','now')")
        conn.commit()
    finally:
        conn.close()


def test_concurrent_initialization(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"

    def open_cache(_):
        conn = connect_cache(path)
        try:
            return conn.execute("SELECT count(*) FROM vol_regime_days").fetchone()[0]
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(open_cache, range(8))) == [0] * 8
