"""Historical date discovery for vol regime."""

from datetime import date
from pathlib import Path

import pandas as pd

from options_monitor.tabs.vol.vol_regime import (
    _available_sample_dates,
    _load_daily_snapshots_for_expiry,
)


def test_unindexed_local_parquet_is_included_but_raw_csv_is_not(tmp_path: Path) -> None:
    compacted_date = date(2026, 10, 14)
    raw_date = date(2026, 10, 15)
    compacted_dir = tmp_path / "2026" / "10" / "14"
    raw_dir = tmp_path / "2026" / "10" / "15"
    compacted_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (compacted_dir / "GLD_samples_2026-10-14.parquet").touch()
    (raw_dir / "GLD_exp2026-11-13_2026-10-15_20-00-00.csv").touch()

    dates = _available_sample_dates("GLD", [], tmp_path, compacted_date, raw_date)

    assert dates == [compacted_date]


def test_daily_history_uses_first_sample_after_open_hour_and_last(tmp_path: Path) -> None:
    sample_date = date(2026, 10, 14)
    expiry = date(2026, 11, 13)
    day_dir = tmp_path / "2026" / "10" / "14"
    day_dir.mkdir(parents=True)
    path = day_dir / "GLD_samples_2026-10-14.parquet"
    times = pd.to_datetime(
        [
            "2026-10-14T14:20:00Z",  # 10:20 ET: too early
            "2026-10-14T14:35:00Z",  # first after 10:30 ET
            "2026-10-14T17:00:00Z",
            "2026-10-14T19:49:00Z",  # last of the day
        ],
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

    frames = _load_daily_snapshots_for_expiry("GLD", sample_date, expiry, str(tmp_path))

    assert len(frames) == 2
    assert [frame["sampled_at"].iloc[0] for frame in frames] == [times[1], times[3]]


def test_daily_history_does_not_duplicate_lone_late_sample(tmp_path: Path) -> None:
    sample_date = date(2026, 10, 14)
    expiry = date(2026, 11, 13)
    day_dir = tmp_path / "2026" / "10" / "14"
    day_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "sampled_at": pd.to_datetime(["2026-10-14T19:49:00Z"], utc=True),
            "expiration_date": [expiry],
            "contract_type": ["put"],
            "underlying_price": [100.0],
        }
    ).to_parquet(day_dir / "GLD_samples_2026-10-14.parquet")

    frames = _load_daily_snapshots_for_expiry("GLD", sample_date, expiry, str(tmp_path))

    assert len(frames) == 1
