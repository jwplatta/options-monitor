"""Tests for options_monitor.calc.vol_regime."""

from __future__ import annotations

import pandas as pd
import pytest

from options_monitor.calc.vol_regime import (
    VolRegimePoint,
    build_vol_regime_row,
    compute_atm_iv,
    zscore,
)


class TestZscore:
    def test_basic(self) -> None:
        result = zscore(10.0, [8.0, 9.0, 10.0, 11.0, 12.0])
        assert result is not None
        assert result == pytest.approx(0.0, abs=0.01)

    def test_positive_zscore(self) -> None:
        result = zscore(12.0, [8.0, 9.0, 10.0, 11.0, 12.0])
        assert result is not None
        assert result > 0

    def test_negative_zscore(self) -> None:
        result = zscore(7.0, [8.0, 9.0, 10.0, 11.0, 12.0])
        assert result is not None
        assert result < 0

    def test_insufficient_data(self) -> None:
        assert zscore(10.0, [9.0, 11.0]) is None

    def test_zero_std(self) -> None:
        assert zscore(5.0, [5.0, 5.0, 5.0, 5.0]) is None

    def test_nan_filtered(self) -> None:
        result = zscore(10.0, [8.0, float("nan"), 10.0, 12.0])
        assert result is not None


class TestComputeAtmIv:
    def _make_chain(self, spot: float = 100.0) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0, 95.0, 100.0, 105.0],
                "volatility": [22.0, 20.0, 18.0, 24.0, 21.0, 19.0],
                "contract_type": ["CALL", "CALL", "CALL", "PUT", "PUT", "PUT"],
            }
        )

    def test_averages_call_put(self) -> None:
        iv = compute_atm_iv(self._make_chain(), 100.0)
        assert iv is not None
        assert iv == pytest.approx(20.5)  # avg of 20 (call) and 21 (put)

    def test_off_center_spot(self) -> None:
        iv = compute_atm_iv(self._make_chain(), 104.0)
        assert iv is not None
        # nearest strike is 105
        assert iv == pytest.approx(18.5)  # avg of 18 and 19

    def test_empty_df(self) -> None:
        assert compute_atm_iv(pd.DataFrame(), 100.0) is None

    def test_zero_spot(self) -> None:
        assert compute_atm_iv(self._make_chain(), 0.0) is None


class TestBuildVolRegimeRow:
    def test_returns_point(self) -> None:
        hist_ivs = [18.0, 19.0, 20.0, 21.0, 22.0]
        hist_rrs = [-2.0, -1.0, 0.0, 1.0, 2.0]
        result = build_vol_regime_row(20.0, 0.0, hist_ivs, hist_rrs)
        assert result is not None
        assert isinstance(result, VolRegimePoint)
        assert result.iv_zscore == pytest.approx(0.0, abs=0.01)
        assert result.rr_zscore == pytest.approx(0.0, abs=0.01)

    def test_insufficient_history(self) -> None:
        assert build_vol_regime_row(20.0, 0.0, [19.0], [1.0]) is None
