"""Tests for volatility calculation functions."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from tractatus.calc.vol import expected_move, iv_rv_spread, realized_vol, vix_spx_correlation


def test_realized_vol_shape_and_sanity(candle_dir: Path) -> None:
    spx = pd.read_csv(candle_dir / "SPX_day.csv", parse_dates=["datetime"])
    rv = realized_vol(spx["close"], window=30)
    assert rv.shape == spx["close"].shape
    valid = rv.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()
    assert (valid < 200).all()


def test_realized_vol_9day(candle_dir: Path) -> None:
    spx = pd.read_csv(candle_dir / "SPX_day.csv", parse_dates=["datetime"])
    rv9 = realized_vol(spx["close"], window=9)
    assert len(rv9.dropna()) > 0


def test_iv_rv_spread_elementwise() -> None:
    iv = pd.Series([20.0, 22.0, 18.0])
    rv = pd.Series([15.0, 14.0, 16.0])
    spread = iv_rv_spread(iv, rv)
    expected = pd.Series([5.0, 8.0, 2.0])
    pd.testing.assert_series_equal(spread, expected)


def test_vix_spx_correlation_returns_float(candle_dir: Path) -> None:
    spx = pd.read_csv(candle_dir / "SPX_day.csv", parse_dates=["datetime"])
    vix = pd.read_csv(candle_dir / "VIX_day.csv", parse_dates=["datetime"])
    corr = vix_spx_correlation(spx, vix)
    assert -1.0 <= corr <= 1.0


def test_expected_move_symmetric() -> None:
    lower, upper = expected_move(spot=5300.0, vix9d_close=15.0)
    assert lower < 5300.0 < upper
    assert abs(upper - 5300.0) == pytest.approx(abs(5300.0 - lower))
