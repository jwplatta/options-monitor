"""OI and Fixed Strike request historical data for their chosen lookback."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd

from options_monitor.tabs import oi
from options_monitor.tabs.vol import fixed_strike


def test_oi_historical_range(monkeypatch) -> None:
    loader = MagicMock(return_value=pd.DataFrame())
    monkeypatch.setattr(oi, "load_historical_sample_window", loader)
    assert oi._load_oi_historical_frames("SPXW", 30, 60) == ([], [])
    loader.assert_called_once_with("SPXW", date.today() - timedelta(days=30), 60)


def test_fixed_strike_historical_range(monkeypatch) -> None:
    loader = MagicMock(return_value=pd.DataFrame())
    monkeypatch.setattr(fixed_strike, "load_historical_sample_window", loader)
    assert fixed_strike._load_historical_frames("SPXW", 90, 30) == ([], [])
    loader.assert_called_once_with("SPXW", date.today() - timedelta(days=90), 30)
