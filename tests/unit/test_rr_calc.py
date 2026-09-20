"""Unit tests for compute_risk_reversal in calc/vol.py."""

from __future__ import annotations

import pandas as pd
import pytest
from tractatus.calc.vol import RiskReversalResult, compute_risk_reversal


@pytest.fixture()
def synthetic_opts() -> pd.DataFrame:
    """Minimal options chain with known 25D strikes for deterministic assertions."""
    return pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "CALL", "PUT", "PUT", "PUT"],
            "delta": [0.50, 0.25, 0.10, -0.10, -0.25, -0.50],
            "volatility": [15.0, 18.0, 22.0, 22.5, 20.0, 16.0],
            "strike": [5200.0, 5300.0, 5400.0, 5100.0, 5000.0, 4900.0],
            "open_interest": [100.0, 200.0, 150.0, 150.0, 200.0, 100.0],
            "expiration_date": ["2026-05-16"] * 6,
        }
    )


def test_rr_returns_named_tuple(synthetic_opts: pd.DataFrame) -> None:
    result = compute_risk_reversal(synthetic_opts)
    assert result is not None
    assert isinstance(result, RiskReversalResult)


def test_rr_value_correct(synthetic_opts: pd.DataFrame) -> None:
    result = compute_risk_reversal(synthetic_opts)
    assert result is not None
    # 25D call IV=18.0, 25D put IV=20.0 → RR = 18.0 - 20.0 = -2.0
    assert result.rr == pytest.approx(-2.0)


def test_rr_25d_call_iv(synthetic_opts: pd.DataFrame) -> None:
    result = compute_risk_reversal(synthetic_opts)
    assert result is not None
    assert result.iv_25d_call == pytest.approx(18.0)


def test_rr_25d_put_iv(synthetic_opts: pd.DataFrame) -> None:
    result = compute_risk_reversal(synthetic_opts)
    assert result is not None
    assert result.iv_25d_put == pytest.approx(20.0)


def test_rr_strike_selection(synthetic_opts: pd.DataFrame) -> None:
    result = compute_risk_reversal(synthetic_opts)
    assert result is not None
    assert result.strike_25d_call == pytest.approx(5300.0)
    assert result.strike_25d_put == pytest.approx(5000.0)


def test_rr_returns_none_when_no_calls(synthetic_opts: pd.DataFrame) -> None:
    no_calls = synthetic_opts[synthetic_opts["contract_type"] == "PUT"].copy()
    assert compute_risk_reversal(no_calls) is None


def test_rr_returns_none_when_no_puts(synthetic_opts: pd.DataFrame) -> None:
    no_puts = synthetic_opts[synthetic_opts["contract_type"] == "CALL"].copy()
    assert compute_risk_reversal(no_puts) is None


def test_rr_returns_none_missing_column() -> None:
    bad_df = pd.DataFrame({"contract_type": ["CALL"], "delta": [0.25]})
    assert compute_risk_reversal(bad_df) is None


def test_rr_returns_none_when_all_iv_zero(synthetic_opts: pd.DataFrame) -> None:
    df = synthetic_opts.copy()
    df["volatility"] = 0.0
    assert compute_risk_reversal(df) is None


def test_rr_interpolates_between_brackets() -> None:
    """IV should be linearly interpolated when no row has exactly delta=0.25."""
    df = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "PUT", "PUT"],
            # Call deltas bracket 0.25; put deltas bracket -0.25
            "delta": [0.20, 0.30, -0.20, -0.30],
            # IV at 0.20 = 16.0, at 0.30 = 18.0 → interp at 0.25 = 17.0
            # IV at -0.20 = 22.0, at -0.30 = 20.0 → interp at -0.25 = 21.0
            "volatility": [16.0, 18.0, 22.0, 20.0],
            "strike": [5300.0, 5250.0, 5100.0, 5050.0],
            "expiration_date": ["2026-05-16"] * 4,
        }
    )
    result = compute_risk_reversal(df)
    assert result is not None
    assert result.iv_25d_call == pytest.approx(17.0)
    assert result.iv_25d_put == pytest.approx(21.0)
    assert result.rr == pytest.approx(-4.0)


def test_rr_expiry_filter(synthetic_opts: pd.DataFrame) -> None:
    """Filter to correct expiry when combined frame has multiple expirations."""
    extra = synthetic_opts.copy()
    extra["expiration_date"] = "2026-05-23"
    extra["theoretical_volatility"] = 99.0
    combined = pd.concat([synthetic_opts, extra], ignore_index=True)
    result = compute_risk_reversal(combined, expiry="2026-05-16")
    assert result is not None
    assert result.iv_25d_call == pytest.approx(18.0)  # not 99.0
    assert result.iv_25d_put == pytest.approx(20.0)
