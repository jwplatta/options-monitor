"""Persistent historical observations and live Vol Regime freshness."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from options_monitor.data.sqlite_cache import cache_path
from options_monitor.data.vol_regime_cache import VolRegimeObservationStore
from options_monitor.tabs.vol import vol_regime


def test_observations_are_versioned_by_remote_revision_and_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    day = date(2026, 10, 14)
    rows = [("2026-10-14T14:35:00+00:00", 21.0, -2.0)]
    with VolRegimeObservationStore(path, "source-a") as store:
        store.put("SPY", day, 30, "etag1:100", rows)
    with VolRegimeObservationStore(path, "source-a") as store:
        assert store.revisions("SPY", 30) == {day.isoformat(): "etag1:100"}
        assert store.get_range("SPY", 30, day, day + timedelta(days=1)) == ([21.0], [-2.0], day)
        store.put("SPY", day, 30, "etag2:100", [])
        assert store.get_range("SPY", 30, day, day + timedelta(days=1)) == ([], [], None)
        assert store.revisions("SPY", 30) == {day.isoformat(): "etag2:100"}
    with VolRegimeObservationStore(path, "source-b") as store:
        assert store.revisions("SPY", 30) == {}


def test_cleanup_cascades_and_keeps_boundary(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    cutoff = date(2025, 10, 28)
    with VolRegimeObservationStore(path) as store:
        for day in [cutoff - timedelta(days=1), cutoff]:
            store.put("SPY", day, 30, "v1", [(day.isoformat(), 20.0, 1.0)])
        generation = store.generation("SPY")
        store.cleanup(cutoff)
        assert store.revisions("SPY", 30) == {cutoff.isoformat(): "v1"}
        assert store.get_range(
            "SPY", 30, cutoff - timedelta(days=10), cutoff + timedelta(days=1)
        ) == ([20.0], [1.0], cutoff)
        assert store.generation("SPY") > generation


def test_cache_path_is_separate_from_tractatus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TRACTATUS_CACHE_DIR", str(tmp_path / "tractatus"))
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "options-monitor"))
    assert cache_path() == tmp_path / "options-monitor" / "options_monitor_cache.sqlite3"


def test_current_chain_is_loaded_again_on_each_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date.today()
    expiry = today + timedelta(days=30)
    reader = MagicMock()
    reader.list_option_sample_dates.return_value = [today - timedelta(days=1)]
    reader.latest_snapshots.return_value = {expiry: "s3://bucket/latest.csv"}
    reader.load_intraday_snapshot.side_effect = [
        pd.DataFrame(
            {
                "expiration_date": [expiry],
                "underlying_price": [100.0],
                "strike": [100.0],
                "volatility": [iv],
                "contract_type": ["CALL"],
            }
        )
        for iv in (20.0, 30.0)
    ]
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    monkeypatch.setattr(vol_regime, "compute_risk_reversal", lambda _df: SimpleNamespace(rr=1.0))
    monkeypatch.setattr(
        vol_regime.vol_regime_jobs, "available_dates", lambda *_args: [today - timedelta(days=1)]
    )
    monkeypatch.setattr(
        vol_regime.vol_regime_jobs,
        "history",
        lambda *_args: ([15.0] * 3, [0.0] * 3, today - timedelta(days=1)),
    )

    first = vol_regime._compute_vol_regime_data(("SPY",), 30, 60)
    second = vol_regime._compute_vol_regime_data(("SPY",), 30, 60)
    assert first.iloc[0]["current_iv"] == 20.0
    assert second.iloc[0]["current_iv"] == 30.0
    assert reader.latest_snapshots.call_count == 2
    assert reader.load_intraday_snapshot.call_count == 2


def test_data_table_includes_cache_status_for_unplotted_roots(monkeypatch) -> None:
    from contextlib import nullcontext

    tables = []
    monkeypatch.setattr(vol_regime.st, "expander", lambda *args: nullcontext())
    monkeypatch.setattr(vol_regime.st, "dataframe", lambda frame, **kwargs: tables.append(frame))
    data = pd.DataFrame([{"symbol": "QQQ", "current_iv": 20.0}])
    states = {
        "QQQ": {"status": "ready", "completed_at": "2026-10-29T15:27:40+00:00"},
        "SPY": {"status": "queued"},
    }
    vol_regime._render_data_table(data, ["QQQ", "SPY"], states)
    assert list(tables[0].index) == ["QQQ", "SPY"]
    assert tables[0].loc["QQQ", "Historical cache"] == "ready"
    assert tables[0].loc["QQQ", "Last verified (UTC)"] == "2026-10-29T15:27:40+00:00"
    assert tables[0].loc["SPY", "Historical cache"] == "queued"
