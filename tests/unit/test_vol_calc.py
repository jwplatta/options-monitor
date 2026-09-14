"""Tests for volatility calculation functions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from options_monitor.calc.vol import expected_move, iv_rv_spread, realized_vol, vix_spx_correlation
from options_monitor.data.candles import load_candles


def test_realized_vol_shape_and_sanity(candle_dir: Path) -> None:
    spx = load_candles("SPX", "day", data_dir=candle_dir, start=date(2026, 1, 1))
    rv = realized_vol(spx["close"], window=30)
    assert rv.shape == spx["close"].shape
    valid = rv.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()
    assert (valid < 200).all()


def test_realized_vol_9day(candle_dir: Path) -> None:
    spx = load_candles("SPX", "day", data_dir=candle_dir)
    rv9 = realized_vol(spx["close"], window=9)
    assert len(rv9.dropna()) > 0


def test_iv_rv_spread_elementwise() -> None:
    iv = pd.Series([20.0, 22.0, 18.0])
    rv = pd.Series([15.0, 14.0, 16.0])
    spread = iv_rv_spread(iv, rv)
    expected = pd.Series([5.0, 8.0, 2.0])
    pd.testing.assert_series_equal(spread, expected)


def test_vix_spx_correlation_returns_float(candle_dir: Path) -> None:
    spx = load_candles("SPX", "day", data_dir=candle_dir, start=date(2026, 1, 1))
    vix = load_candles("VIX", "day", data_dir=candle_dir, start=date(2026, 1, 1))
    corr = vix_spx_correlation(spx, vix)
    assert -1.0 <= corr <= 1.0


def test_expected_move_symmetric() -> None:
    lower, upper = expected_move(spot=5300.0, vix9d_close=15.0)
    assert lower < 5300.0 < upper
    assert abs(upper - 5300.0) == pytest.approx(abs(5300.0 - lower))
