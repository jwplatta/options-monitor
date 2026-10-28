"""Persistence, scheduling, retries, and remote-free historical range reads."""

from contextlib import nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from options_monitor.data import vol_regime_jobs
from options_monitor.data.cache_jobs import CacheJobs, JobDefinition
from options_monitor.data.vol_regime_cache import VolRegimeObservationStore


def jobs_at(tmp_path):
    return CacheJobs("http://minio:9000", "lake", path=tmp_path / "cache.sqlite3")


def test_requests_deduplicate_and_prioritize_users_and_persist_settings(tmp_path):
    jobs = jobs_at(tmp_path)
    computed = []
    jobs.register(
        JobDefinition(
            "demo", 1, {}, lambda p: p, lambda root, p: computed.append(root), lambda cutoff: None
        )
    )
    jobs.set_targets("demo", ["SPXW"], {})
    jobs.request("demo", "TSLA", {})
    jobs.request("demo", "TSLA", {})
    assert jobs.tick()
    assert computed == ["TSLA"]
    assert jobs.tick()
    assert computed == ["TSLA", "SPXW"]
    assert not jobs.tick()
    assert jobs.targets("demo") == ["SPXW"]
    jobs.set_setting("demo:retention_days", 720)
    reopened = jobs_at(tmp_path)
    assert reopened.retention("demo") == 720
    assert reopened.targets("demo") == ["SPXW"]


def test_failure_keeps_retry_backoff_and_restart_recovers_running(tmp_path):
    jobs = jobs_at(tmp_path)
    compute = MagicMock(side_effect=RuntimeError("unavailable"))
    jobs.register(JobDefinition("demo", 1, {}, lambda p: p, compute, lambda cutoff: None))
    jobs.set_targets("demo", [], {})
    jobs.request("demo", "SPY", {})
    jobs.tick()
    assert jobs.state("demo", "SPY", {})["status"] == "failed"
    jobs.request("demo", "SPY", {})
    assert not jobs.tick()
    assert compute.call_count == 1
    with jobs.connection() as db:
        db.execute("UPDATE cache_job_state SET status='running'")
    reopened = jobs_at(tmp_path)
    assert reopened.state("demo", "SPY", {})["status"] == "queued"


def test_cleanup_once_daily_and_retention_cutoff(tmp_path, monkeypatch):
    today = date(2026, 10, 28)
    monkeypatch.setattr("options_monitor.data.cache_jobs.market_today", lambda: today)
    jobs = jobs_at(tmp_path)
    cleanups = []
    jobs.register(
        JobDefinition(
            "demo", 1, {}, lambda p: p, lambda r, p: None, cleanups.append, default_roots=()
        )
    )
    jobs.tick()
    jobs.tick()
    assert cleanups == [today - timedelta(days=365)]


def test_vol_job_revision_reuse_empty_days_and_remote_free_ranges(tmp_path, monkeypatch):
    jobs = jobs_at(tmp_path)
    day = date(2026, 10, 27)
    source = SimpleNamespace(
        sample_date=day, uri="s3://lake/file.parquet", revision="v1:100", size_bytes=100
    )
    reader = MagicMock()
    reader.list_option_sources.return_value = [source]
    reader.query_connection.side_effect = lambda: nullcontext(object())
    reader.option_daily_snapshots.return_value = pd.DataFrame(
        {
            "sampled_at": pd.to_datetime(["2026-10-27T14:35Z", "2026-10-27T20:00Z"]),
            "expiration_date": ["2026-11-27"] * 2,
            "strike": [100.0, 100.0],
            "volatility": [20.0, 25.0],
            "contract_type": ["CALL", "CALL"],
            "underlying_price": [100.0, 100.0],
            "delta": [0.25, 0.25],
        }
    )
    monkeypatch.setattr(vol_regime_jobs, "CacheReader", lambda: reader)
    monkeypatch.setattr(vol_regime_jobs, "market_today", lambda: day + timedelta(days=1))
    monkeypatch.setattr(
        vol_regime_jobs, "compute_risk_reversal", lambda df: SimpleNamespace(rr=1.0)
    )
    vol_regime_jobs.register_vol_regime(jobs)
    compute = jobs.definitions["vol_regime"].compute
    compute("SPY", {"target_dte": 30})
    compute("SPY", {"target_dte": 30})
    assert reader.option_daily_snapshots.call_count == 1
    with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
        assert store.get_range("SPY", 30, day, day + timedelta(days=1)) == (
            [20.0, 25.0],
            [1.0, 1.0],
            day,
        )
    monkeypatch.setattr(vol_regime_jobs, "runtime", lambda: jobs)
    reader.reset_mock()
    assert vol_regime_jobs.history("SPY", 30, day, day + timedelta(days=1))[:2] == (
        [20.0, 25.0],
        [1.0, 1.0],
    )
    reader.list_option_sources.assert_not_called()
    reader.option_daily_snapshots.assert_not_called()
    source.revision = "v2:100"
    reader.option_daily_snapshots.return_value = pd.DataFrame(columns=["sampled_at"])
    compute("SPY", {"target_dte": 30})
    with VolRegimeObservationStore(jobs.path, jobs.namespace) as store:
        assert store.revisions("SPY", 30) == {day.isoformat(): "v2:100"}
        assert store.get_range("SPY", 30, day, day + timedelta(days=1)) == ([], [], None)


def test_invalid_params_rejected_without_enqueuing(tmp_path):
    jobs = jobs_at(tmp_path)
    vol_regime_jobs.register_vol_regime(jobs)
    with pytest.raises(ValueError):
        jobs.request("vol_regime", "SPY", {"target_dte": -1})
