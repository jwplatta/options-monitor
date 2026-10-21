"""Historical and intraday options loader contracts."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pandas as pd

from options_monitor.data.options import (
    list_expirations_for_window_on_date,
    list_snapshot_dates_for_expiry,
    load_historical_sample_window,
    load_latest_archived_window,
    load_latest_historical_sample_per_date,
    load_options_snapshot,
    parquet_path_for_date,
)


def test_intraday_snapshot_uses_reader() -> None:
    reader = MagicMock()
    expected = pd.DataFrame({"strike": [5000]})
    reader.load_intraday_snapshot.return_value = expected
    assert load_options_snapshot("s3://tickrake-intraday/snap.csv", _reader=reader).equals(expected)
    reader.load_intraday_snapshot.assert_called_once_with("s3://tickrake-intraday/snap.csv")


def test_expiry_dates_are_derived_from_cached_parquets(tmp_path: Path) -> None:
    reader = MagicMock()
    expiry = date(2026, 4, 18)
    first, second = date(2026, 4, 14), date(2026, 4, 15)
    reader.list_sample_dates.return_value = [first, second]
    reader.get_parquet.side_effect = [None, tmp_path / "cached.parquet"]
    reader.options_query.list_snapshot_times.return_value = [datetime(2026, 4, 15, 15)]
    assert list_snapshot_dates_for_expiry("SPXW", expiry, _reader=reader) == [second]
    reader.options_query.list_snapshot_times.assert_called_once_with(
        tmp_path / "cached.parquet", expiry
    )


def test_expirations_window_uses_reader_query(tmp_path: Path) -> None:
    reader = MagicMock()
    reader.get_parquet.return_value = tmp_path / "cached.parquet"
    reader.options_query.list_expirations.return_value = [date(2026, 4, 16), date(2026, 4, 18)]
    assert list_expirations_for_window_on_date(
        "SPXW", date(2026, 4, 15), 2, False, _reader=reader
    ) == [date(2026, 4, 16)]
    reader.options_query.list_expirations.assert_called_once_with(
        tmp_path / "cached.parquet", date(2026, 4, 16)
    )


def test_archive_miss_returns_none() -> None:
    reader = MagicMock()
    reader.list_sample_dates.return_value = [date(2026, 4, 15)]
    reader.get_parquet.return_value = None
    assert parquet_path_for_date("SPXW", date(2026, 4, 15), _reader=reader) is None
    assert load_latest_archived_window("SPXW", date(2026, 4, 15), 5, _reader=reader) is None


def test_historical_window_caches_range_before_query(tmp_path: Path) -> None:
    reader = MagicMock()
    path = tmp_path / "2026" / "04" / "15"
    path.mkdir(parents=True)
    (path / "SPXW_samples_2026-04-15.parquet").touch()
    reader.ensure_parquet_files.return_value = [
        str(tmp_path / "2026" / "04" / "15" / "SPXW.parquet")
    ]
    reader.options_query.load_sample_window.return_value = pd.DataFrame({"strike": [5000]})
    columns = ["sampled_at", "strike"]
    result = load_historical_sample_window(
        "SPXW", date(2026, 4, 1), 30, columns=columns, _reader=reader
    )
    reader.ensure_parquet_files.assert_called_once_with("SPXW", date(2026, 4, 1), date.today())
    reader.options_query.load_sample_window.assert_called_once_with(
        reader.ensure_parquet_files.return_value, date(2026, 4, 1), 30, columns=columns
    )
    assert len(result) == 1


def test_latest_historical_sample_per_date_selects_latest_chain_per_expiry(
    tmp_path: Path,
) -> None:
    reader = MagicMock()
    prior_date, sample_date = date(2026, 3, 31), date(2026, 4, 1)
    parquet_path = tmp_path / f"{sample_date}.parquet"
    with duckdb.connect() as conn:
        conn.execute(
            "COPY (SELECT * FROM (VALUES "
            "(TIMESTAMPTZ '2026-04-01 14:00:00+00', DATE '2026-04-17', 10), "
            "(TIMESTAMPTZ '2026-04-01 13:30:00+00', DATE '2026-04-17', 20), "
            "(TIMESTAMPTZ '2026-04-01 13:45:00+00', DATE '2026-04-24', 30), "
            "(TIMESTAMPTZ '2026-04-01 14:15:00+00', DATE '2026-04-24', 40)"
            ") AS t(sampled_at, expiration_date, open_interest)) TO ? (FORMAT PARQUET)",
            [str(parquet_path)],
        )
    reader.ensure_parquet_files.return_value = [str(parquet_path)]
    columns = ["sampled_at", "expiration_date", "open_interest"]
    result = load_latest_historical_sample_per_date(
        "SPXW", prior_date, columns=columns, _reader=reader
    )

    assert len(result) == 2
    assert result["sampled_at"].tolist() == [
        pd.Timestamp("2026-04-01 14:00:00+00:00"),
        pd.Timestamp("2026-04-01 14:15:00+00:00"),
    ]
    assert result["open_interest"].tolist() == [10, 40]
    assert pd.to_datetime(result["sample_date"]).dt.date.tolist() == [sample_date, sample_date]
    assert list(result.columns) == [*columns, "sample_date"]
    reader.ensure_parquet_files.assert_called_once_with("SPXW", prior_date, date.today())
