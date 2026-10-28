"""Candle loader preserves provider and date filtering."""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from options_monitor.data.candles import list_available_dates, load_candles

_CANDLES = pd.DataFrame(
    {
        "datetime": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "open": [1.0] * 3,
        "high": [2.0] * 3,
        "low": [0.5] * 3,
        "close": [1.5] * 3,
        "volume": [100.0] * 3,
    }
)


def test_candles_use_ibkr_paper_and_filter_dates() -> None:
    reader = MagicMock()
    reader.candles.return_value = _CANDLES
    assert (
        len(
            load_candles("SPX", "day", start=date(2026, 1, 2), end=date(2026, 1, 2), _reader=reader)
        )
        == 1
    )
    assert list_available_dates("SPX", "day", _reader=reader)[0].date() == date(2026, 1, 1)
    reader.candles.assert_called_once_with("ibkr-paper", symbols=["SPX"], frequency="day")


def test_missing_candle_file_propagates() -> None:
    reader = MagicMock()
    reader.candles.side_effect = FileNotFoundError("missing")
    with pytest.raises(FileNotFoundError):
        load_candles("UNKNOWN", "day", _reader=reader)
