"""Reader-backed intraday dashboard helpers."""

from datetime import date, datetime
from unittest.mock import MagicMock

from options_monitor.data.intraday_options import (
    find_intraday_updated_at,
    find_latest_snapshots,
    find_series_snapshots,
    list_expirations,
)


def test_intraday_expiry_window_and_reader_calls() -> None:
    reader = MagicMock()
    start = date(2026, 4, 15)
    reader.latest_snapshots.return_value = {date(2026, 4, 17): "s3://bucket/snap.csv"}
    reader.series_snapshots.return_value = [{"expiration_date": "2026-04-17"}]
    reader.list_intraday_expirations.return_value = [date(2026, 4, 17)]
    reader.intraday_updated_at.return_value = datetime(2026, 4, 15, 15)

    assert list_expirations("SPXW", _reader=reader) == [date(2026, 4, 17)]
    assert find_intraday_updated_at("SPXW", _reader=reader) == datetime(2026, 4, 15, 15)
    assert find_latest_snapshots("SPXW", start, 2, False, _reader=reader)
    reader.latest_snapshots.assert_called_once_with("SPXW", date(2026, 4, 16), date(2026, 4, 17))
    assert find_series_snapshots("SPXW", start, 2, _reader=reader)
    reader.series_snapshots.assert_called_once_with("SPXW", start, date(2026, 4, 17))


def test_empty_expiry_window_skips_reader() -> None:
    reader = MagicMock()
    assert find_latest_snapshots("SPXW", date(2026, 4, 15), 0, False, _reader=reader) == {}
    assert find_series_snapshots("SPXW", date(2026, 4, 15), 0, False, _reader=reader) == []
    reader.assert_not_called()
