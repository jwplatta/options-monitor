"""Candle loader preserves provider and date filtering."""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from options_monitor.data.candles import list_available_dates, load_candles


def test_candles_use_ibkr_paper_and_filter_dates() -> None:
    reader = MagicMock()
    reader.load_candles.return_value = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "open": [1.0] * 3,
            "high": [2.0] * 3,
            "low": [0.5] * 3,
            "close": [1.5] * 3,
            "volume": [100.0] * 3,
        }
    )
    assert (
        len(
            load_candles("SPX", "day", start=date(2026, 1, 2), end=date(2026, 1, 2), _reader=reader)
        )
        == 1
    )
    assert list_available_dates("SPX", "day", _reader=reader)[0].date() == date(2026, 1, 1)
    reader.load_candles.assert_called_once_with("SPX", "day", provider="ibkr-paper")


def test_missing_candle_file_propagates() -> None:
    reader = MagicMock()
    reader.load_candles.side_effect = FileNotFoundError("missing")
    with pytest.raises(FileNotFoundError):
        load_candles("UNKNOWN", "day", _reader=reader)
