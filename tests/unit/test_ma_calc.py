"""Tests for moving average calculation functions."""

from __future__ import annotations

import pandas as pd
import pytest
from tractatus.calc.ma import sma, validate_windows


def test_sma_basic() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, window=3)
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_sma_first_values_are_nan() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = sma(s, window=3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])


def test_validate_windows_raises_when_fast_gte_slow() -> None:
    with pytest.raises(ValueError, match="fast"):
        validate_windows(fast=10, slow=5)


def test_validate_windows_raises_when_equal() -> None:
    with pytest.raises(ValueError, match="fast"):
        validate_windows(fast=10, slow=10)


def test_validate_windows_passes_valid() -> None:
    validate_windows(fast=5, slow=20)
