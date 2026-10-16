"""Historical date discovery for vol regime."""

from datetime import date
from pathlib import Path

from options_monitor.tabs.vol.vol_regime import _available_sample_dates


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
