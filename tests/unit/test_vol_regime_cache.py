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


def test_observations_survive_reopen_and_invalidate_when_source_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "observations.sqlite3"
    source = tmp_path / "SPY.parquet"
    source.write_bytes(b"version one")
    sample_date = date(2026, 10, 14)
    rows = [("2026-10-14 14:35:00+00:00", 21.0, -2.0)]

    with VolRegimeObservationStore(db_path) as store:
        assert store.get("SPY", sample_date, 30) is None
        store.put("SPY", sample_date, 30, source, rows)
        assert store.get("SPY", sample_date, 30) == rows
        assert store.get("SPY", sample_date, 45) is None

    with VolRegimeObservationStore(db_path) as store:
        assert store.get("SPY", sample_date, 30) == rows

    source.write_bytes(b"version two is longer")
    with VolRegimeObservationStore(db_path) as store:
        assert store.get("SPY", sample_date, 30) is None
        store.put("SPY", sample_date, 30, source, [])
        assert store.get("SPY", sample_date, 30) == []


def test_cache_path_is_separate_from_tractatus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TRACTATUS_CACHE_DIR", str(tmp_path / "tractatus"))
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "options-monitor"))
    assert cache_path() == tmp_path / "options-monitor" / "options_monitor_cache.sqlite3"


def test_historical_series_reuses_persisted_observations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "GLD.parquet"
    source.write_bytes(b"immutable source")
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path))
    reader = MagicMock()
    reader.get_parquet.return_value = source
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    compute = MagicMock(return_value=[("snapshot", 25.0, -1.5)])
    monkeypatch.setattr(vol_regime, "_historical_observations", compute)
    sample_date = date(2026, 10, 14)

    assert vol_regime._historical_series("GLD", [sample_date], 30) == ([25.0], [-1.5])
    assert vol_regime._historical_series("GLD", [sample_date], 30) == ([25.0], [-1.5])
    reader.get_parquet.assert_called_once_with("GLD", sample_date)
    compute.assert_called_once_with(source, sample_date, 30)


def test_current_chain_is_loaded_again_on_each_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date.today()
    expiry = today + timedelta(days=30)
    reader = MagicMock()
    reader.list_sample_dates.return_value = [today - timedelta(days=1)]
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
    monkeypatch.setattr(vol_regime, "_historical_series", lambda *_args: ([15.0] * 3, [0.0] * 3))

    first = vol_regime._compute_vol_regime_data(("SPY",), 30, 60)
    second = vol_regime._compute_vol_regime_data(("SPY",), 30, 60)
    assert first.iloc[0]["current_iv"] == 20.0
    assert second.iloc[0]["current_iv"] == 30.0
    assert reader.latest_snapshots.call_count == 2
    assert reader.load_intraday_snapshot.call_count == 2
