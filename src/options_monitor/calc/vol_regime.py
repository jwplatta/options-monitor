# TODO: Extract pure calc functions to tractatus.calc.vol_regime
# These functions are intentionally free of I/O and Streamlit dependencies
# so they can move to the tractatus shared library later.
"""Vol regime percentile-rank computation for IV and risk reversal."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
import pandas as pd


class VolRegimePoint(NamedTuple):
    """Single ticker's position on the vol regime scatter."""

    iv_rank: float  # 0–100 percentile
    rr_rank: float  # 0–100 percentile
    current_iv: float
    current_rr: float
    iv_mean: float
    rr_mean: float


def percentile_rank(
    current: float,
    history: Sequence[float],
    min_obs: int = 3,
) -> float | None:
    """Percentile rank (0–100) of *current* within *history*.

    Returns the percentage of historical values that are ≤ current.
    0 = current is at the historical minimum, 100 = at or above the max.
    Returns None when there are fewer than *min_obs* finite observations.
    """
    vals = [v for v in history if math.isfinite(v)]
    if len(vals) < min_obs:
        return None
    count_le = sum(1 for v in vals if v <= current)
    return 100.0 * count_le / len(vals)


def compute_atm_iv(snapshot: pd.DataFrame, spot: float) -> float | None:
    """Return ATM implied volatility from a single-expiry options snapshot.

    Finds the strike nearest to *spot* and averages call + put IV when both
    are available.  The ``volatility`` column is expected to be in percentage
    points (e.g. 25.0 for 25%).

    Parameters
    ----------
    snapshot:
        Options chain DataFrame with at least ``strike``, ``volatility``, and
        ``contract_type`` columns.
    spot:
        Current underlying price.
    """
    required = {"strike", "volatility", "contract_type"}
    if not required.issubset(snapshot.columns):
        return None

    df = snapshot.dropna(subset=["strike", "volatility"]).copy()
    df = df[df["volatility"] > 0]
    if df.empty or spot <= 0:
        return None

    df["contract_type"] = df["contract_type"].str.upper()
    df["dist"] = (df["strike"] - spot).abs()
    nearest_strike = df.loc[df["dist"].idxmin(), "strike"]

    atm = df[df["strike"] == nearest_strike]
    call_iv = atm.loc[atm["contract_type"] == "CALL", "volatility"]
    put_iv = atm.loc[atm["contract_type"] == "PUT", "volatility"]

    ivs: list[float] = []
    if not call_iv.empty:
        ivs.append(float(call_iv.iloc[0]))
    if not put_iv.empty:
        ivs.append(float(put_iv.iloc[0]))

    return float(np.mean(ivs)) if ivs else None


def build_vol_regime_row(
    current_iv: float,
    current_rr: float,
    hist_ivs: Sequence[float],
    hist_rrs: Sequence[float],
) -> VolRegimePoint | None:
    """Build a single ticker's vol-regime point from current and historical values.

    Returns None if either percentile rank cannot be computed (insufficient history).
    """
    iv_pct = percentile_rank(current_iv, hist_ivs)
    rr_pct = percentile_rank(current_rr, hist_rrs)
    if iv_pct is None or rr_pct is None:
        return None

    iv_vals = [v for v in hist_ivs if math.isfinite(v)]
    rr_vals = [v for v in hist_rrs if math.isfinite(v)]

    return VolRegimePoint(
        iv_rank=iv_pct,
        rr_rank=rr_pct,
        current_iv=current_iv,
        current_rr=current_rr,
        iv_mean=float(np.mean(iv_vals)) if iv_vals else 0.0,
        rr_mean=float(np.mean(rr_vals)) if rr_vals else 0.0,
    )
