"""Committed YAML is the source of truth for the relational root registry."""

import pytest

from options_monitor.data import option_root_config, roots
from options_monitor.data.cache_jobs import CacheJobs
from options_monitor.data.sqlite_cache import connect_cache


def test_new_and_reset_caches_are_seeded_without_remote_reads(tmp_path):
    path = tmp_path / "cache.sqlite3"
    conn = connect_cache(path)
    namespace, _ = option_root_config.configured_namespace()
    expected = option_root_config.configured_option_roots()
    assert len(expected) > 0
    assert conn.execute(
        "SELECT option_root,underlying,metadata_json FROM option_roots "
        "WHERE namespace_id=? ORDER BY option_root",
        (namespace,),
    ).fetchall() == list(expected)
    conn.execute("CREATE TABLE obsolete (x TEXT)")
    conn.commit()
    conn.close()
    conn = connect_cache(path)
    assert conn.execute("SELECT count(*) FROM option_roots").fetchone()[0] == len(expected)
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name='obsolete'").fetchall()
    conn.close()


def test_yaml_edits_sync_upserts_and_removed_roots_without_changing_row_identity(
    tmp_path, monkeypatch
):
    path = tmp_path / "cache.sqlite3"
    monkeypatch.setattr(
        option_root_config, "configured_option_roots", lambda: (("SPY", "SPY", "{}"),)
    )
    conn = connect_cache(path)
    rowid = conn.execute("SELECT rowid FROM option_roots WHERE option_root='SPY'").fetchone()[0]
    conn.close()
    monkeypatch.setattr(
        option_root_config,
        "configured_option_roots",
        lambda: (("QQQ", "QQQ", "{}"), ("SPY", "SPY", '{"asset_class": "etf"}')),
    )
    conn = connect_cache(path)
    assert (
        conn.execute("SELECT rowid FROM option_roots WHERE option_root='SPY'").fetchone()[0]
        == rowid
    )
    assert conn.execute("SELECT count(*) FROM option_roots").fetchone()[0] == 2
    conn.close()
    monkeypatch.setattr(
        option_root_config, "configured_option_roots", lambda: (("QQQ", "QQQ", "{}"),)
    )
    conn = connect_cache(path)
    assert conn.execute("SELECT option_root FROM option_roots").fetchall() == [("QQQ",)]
    conn.close()


def test_load_config_preserves_extra_metadata_and_explicit_underlying(tmp_path):
    path = tmp_path / "roots.yaml"
    path.write_text(
        "option_roots:\n  - option_root: SPXW\n    underlying: $SPX\n    asset_class: index\n"
    )
    assert option_root_config.load_option_roots(path) == (
        ("SPXW", "$SPX", '{"asset_class": "index"}'),
    )


@pytest.mark.parametrize(
    "payload",
    [
        "option_roots: [{option_root: SPY}]",
        "option_roots: [{option_root: SPY, underlying: SPY}, {option_root: SPY, underlying: SPY}]",
        "option_roots: wrong",
    ],
)
def test_invalid_config_is_rejected(tmp_path, payload):
    path = tmp_path / "roots.yaml"
    path.write_text(payload)
    with pytest.raises(ValueError):
        option_root_config.load_option_roots(path)


def test_custom_namespace_and_dropdown_read_configured_registry(tmp_path, monkeypatch):
    path = tmp_path / "cache.sqlite3"
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path))
    jobs = CacheJobs("http://other-minio", "other-lake", path=path)
    with jobs.connection() as db:
        assert db.execute(
            "SELECT underlying FROM option_roots WHERE namespace_id=? AND option_root='SPXW'",
            (jobs.namespace,),
        ).fetchone() == ("$SPX",)
    # The dropdown uses the configured default namespace, with no worker startup.
    items, ready = roots.available_roots()
    assert ready
    assert "SPXW" in items


def test_committed_registry_covers_captured_lakehouse_inventory():
    import json
    from pathlib import Path

    snapshot = Path(__file__).parents[1] / "fixtures" / "option_roots" / "lakehouse_2026-10-29.json"
    inventory = json.loads(snapshot.read_text())["option_roots"]
    configured = {
        row[0] for row in option_root_config.load_option_roots(option_root_config.CONFIG_PATH)
    }
    assert set(inventory) <= configured


@pytest.mark.parametrize(
    "root,underlying",
    [
        ("NDX", "$NDX"),
        ("NDXP", "$NDX"),
        ("XSP", "$XSP"),
        ("SPX", "$SPX"),
        ("SPXW", "$SPX"),
        ("RUT", "$RUT"),
        ("RUTW", "$RUT"),
        ("VIX", "$VIX"),
        ("VIXW", "$VIX"),
        ("DJX", "$DJX"),
        ("DJXW", "$DJX"),
    ],
)
def test_index_underlying_mappings(root, underlying):
    configured = {
        r[0]: r[1] for r in option_root_config.load_option_roots(option_root_config.CONFIG_PATH)
    }
    assert configured[root] == underlying
