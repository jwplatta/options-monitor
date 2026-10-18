"""Vol Regime historical reader sources and sampling."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from options_monitor.tabs.vol import vol_regime


def _fixture_parquet(tmp_path: Path) -> tuple[Path, date, date, pd.DatetimeIndex]:
    sample_date = date(2026, 10, 14)
    expiry = date(2026, 11, 13)
    path = tmp_path / "GLD_samples_2026-10-14.parquet"
    times = pd.to_datetime(
        ["2026-10-14T14:20:00Z", "2026-10-14T14:35:00Z", "2026-10-14T19:49:00Z"],
        utc=True,
    )
    pd.DataFrame(
        {
            "sampled_at": times,
            "expiration_date": [expiry] * len(times),
            "contract_type": ["call"] * len(times),
            "underlying_price": [100.0] * len(times),
        }
    ).to_parquet(path)
    return path, sample_date, expiry, times


def test_available_dates_come_from_reader(monkeypatch) -> None:
    reader = MagicMock()
    reader.list_sample_dates.return_value = [date(2026, 10, 13), date(2026, 10, 14)]
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    assert vol_regime._available_sample_dates("GLD", date(2026, 10, 14), date(2026, 10, 15)) == [
        date(2026, 10, 14)
    ]


def test_daily_history_uses_first_post_1030_and_last(monkeypatch, tmp_path: Path) -> None:
    path, sample_date, expiry, times = _fixture_parquet(tmp_path)
    reader = MagicMock()
    reader.get_parquet.return_value = path
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    vol_regime._load_daily_snapshots_for_expiry.clear()
    frames = vol_regime._load_daily_snapshots_for_expiry("GLD", sample_date, expiry)
    assert len(frames) == 2
    assert [frame["sampled_at"].iloc[0] for frame in frames] == [times[1], times[2]]
    reader.get_parquet.assert_called_once_with("GLD", sample_date)


def test_daily_history_missing_parquet(monkeypatch) -> None:
    reader = MagicMock()
    reader.get_parquet.return_value = None
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    vol_regime._load_daily_snapshots_for_expiry.clear()
    assert (
        vol_regime._load_daily_snapshots_for_expiry("GLD", date(2026, 10, 14), date(2026, 11, 13))
        == []
    )


def test_vol_regime_skips_bulk_cache_without_current_data(monkeypatch) -> None:
    reader = MagicMock()
    reader.list_sample_dates.return_value = []
    monkeypatch.setattr(vol_regime, "get_reader", lambda: reader)
    result = vol_regime._compute_vol_regime_data(("GLD",), 30, 60)
    assert result.empty
    reader.ensure_parquet_range.assert_not_called()
