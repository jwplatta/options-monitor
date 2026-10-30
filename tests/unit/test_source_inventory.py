"""Multi-root discovery reuse with real SQLite inventories and source identities."""

from contextlib import nullcontext
from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from tractatus.reader import OptionSource

from options_monitor.data import vol_regime_jobs
from options_monitor.data.cache_jobs import CacheJobs
from options_monitor.data.source_inventory import SourceInventory


def _jobs(tmp_path, endpoint="http://minio"):
    return CacheJobs(endpoint, "lake", path=tmp_path / "inventory.sqlite3")


def _source(root, day=date(2026, 10, 15), revision="etag:100"):
    return OptionSource(day, f"s3://lake/{root}.parquet", revision, 100)


def test_multi_root_inventory_survives_reopen_and_records_empty_roots(tmp_path):
    jobs = _jobs(tmp_path)
    reader = MagicMock()
    source = _source("SPY")
    reader.discover_option_sources.return_value = {"SPY": [source]}
    after, before = date(2026, 10, 1), date(2026, 10, 31)
    assert SourceInventory(jobs).get(reader, ["SPY", "QQQ"], after, before) == {
        "QQQ": [],
        "SPY": [source],
    }
    reader.discover_option_sources.assert_called_once_with(
        ["QQQ", "SPY"], after, before, provider="schwab"
    )
    reopened = _jobs(tmp_path)
    assert SourceInventory(reopened).get(reader, ["SPY"], after, before) == {"SPY": [source]}
    assert SourceInventory(reopened).get(reader, ["QQQ"], after, before) == {"QQQ": []}
    assert reader.discover_option_sources.call_count == 1


def test_new_roots_and_expanded_ranges_refresh_only_missing_coverage(tmp_path):
    jobs = _jobs(tmp_path)
    reader = MagicMock()
    reader.discover_option_sources.return_value = {}
    inventory = SourceInventory(jobs)
    after, before = date(2026, 10, 10), date(2026, 10, 20)
    inventory.get(reader, ["SPY"], after, before)
    inventory.get(reader, ["SPY", "QQQ"], after, before)
    reader.discover_option_sources.assert_called_with(["QQQ"], after, before, provider="schwab")
    inventory.get(reader, ["SPY", "QQQ"], after - timedelta(days=1), before)
    reader.discover_option_sources.assert_called_with(
        ["QQQ", "SPY"], after - timedelta(days=1), before, provider="schwab"
    )
    assert reader.discover_option_sources.call_count == 3


def test_expiration_refreshes_revisions_and_failure_preserves_inventory(tmp_path):
    jobs = _jobs(tmp_path)
    reader = MagicMock()
    source = _source("SPY")
    reader.discover_option_sources.return_value = {"SPY": [source]}
    inventory = SourceInventory(jobs)
    after, before = date(2026, 10, 1), date(2026, 10, 31)
    inventory.get(reader, ["SPY"], after, before)
    with jobs.connection() as db:
        db.execute("UPDATE cache_source_scans SET refreshed_at='2000-01-01T00:00:00+00:00'")
    reader.discover_option_sources.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        inventory.get(reader, ["SPY"], after, before)
    with jobs.connection() as db:
        assert db.execute("SELECT revision FROM cache_sources").fetchone()[0] == "etag:100"
    changed = _source("SPY", revision="new-etag:100")
    reader.discover_option_sources.side_effect = None
    reader.discover_option_sources.return_value = {"SPY": [changed]}
    assert inventory.get(reader, ["SPY"], after, before) == {"SPY": [changed]}


def test_inventory_is_namespaced(tmp_path):
    reader = MagicMock()
    reader.discover_option_sources.return_value = {}
    for endpoint in ("http://one", "http://two"):
        SourceInventory(_jobs(tmp_path, endpoint)).get(
            reader, ["SPY"], date(2026, 1, 1), date(2026, 1, 2)
        )
    assert reader.discover_option_sources.call_count == 2


def test_warmup_jobs_share_discovery_across_symbols_and_dtes(tmp_path, monkeypatch):
    jobs = _jobs(tmp_path)
    today = date(2026, 10, 29)
    monkeypatch.setattr(vol_regime_jobs, "market_today", lambda: today)
    reader = MagicMock()
    reader.discover_option_sources.return_value = {"SPY": [_source("SPY")], "QQQ": [_source("QQQ")]}
    reader.query_connection.side_effect = lambda: nullcontext(object())
    reader.option_daily_snapshots.return_value = pd.DataFrame(columns=["sampled_at"])
    monkeypatch.setattr(vol_regime_jobs, "CacheReader", lambda: reader)
    vol_regime_jobs.register_vol_regime(jobs)
    jobs.set_shared_targets(["SPY", "QQQ"])
    compute = jobs.definitions["vol_regime"].compute
    compute("SPY", {"target_dte": 30})
    compute("QQQ", {"target_dte": 30})
    compute("SPY", {"target_dte": 15})
    reader.discover_option_sources.assert_called_once_with(
        ["QQQ", "SPY"], today - timedelta(days=365), today - timedelta(days=1), provider="schwab"
    )
    assert reader.option_daily_snapshots.call_count == 3
    compute("SPY", {"target_dte": 30})
    assert reader.option_daily_snapshots.call_count == 3
