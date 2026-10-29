"""Pure 25-delta IV interpolation and risk-reversal calculations for charts."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd


class RiskReversalResult(NamedTuple):
    """IVs and RR are percentage points; strikes are interpolated at target delta."""

    rr: float
    iv_25d_call: float
    iv_25d_put: float
    strike_25d_call: float
    strike_25d_put: float


def _at_delta(leg: pd.DataFrame, target: float) -> tuple[float, float]:
    """Interpolate between delta brackets, falling back to the nearest endpoint."""
    ordered = leg.sort_values("delta")
    upper = int(np.searchsorted(ordered["delta"].to_numpy(), target, side="left"))
    if upper == 0 or upper == len(ordered):
        endpoint = ordered.iloc[0 if upper == 0 else -1]
        return float(endpoint["volatility"]), float(endpoint["strike"])
    low, high = ordered.iloc[upper - 1], ordered.iloc[upper]
    span = float(high["delta"] - low["delta"])
    weight = (target - float(low["delta"])) / span if span else 0.0
    return (
        float(low["volatility"] + weight * (high["volatility"] - low["volatility"])),
        float(low["strike"] + weight * (high["strike"] - low["strike"])),
    )


def compute_risk_reversal(
    opts: pd.DataFrame, expiry: str | None = None
) -> RiskReversalResult | None:
    """Return 25Δ call IV minus 25Δ put IV for a single-expiry chain.

    Select the expiry before calling, or provide an ISO date prefix. Numeric
    columns are coerced; missing values and nonpositive IVs are excluded. Each
    leg interpolates both IV and strike at its target delta. An out-of-range
    target (including a single available row) uses the nearest endpoint.
    Returns None when either leg has no usable rows. Does not mutate the input.
    """
    required = {"delta", "volatility", "contract_type", "strike"}
    if not required.issubset(opts.columns):
        return None
    frame = opts.copy()
    if expiry is not None:
        if "expiration_date" not in frame:
            return None
        frame = frame[frame["expiration_date"].astype(str).str.startswith(expiry)].copy()
    for column in ("delta", "volatility", "strike"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(required))
    frame = frame[frame["volatility"] > 0]
    kinds = frame["contract_type"].str.upper()
    calls, puts = frame[kinds == "CALL"], frame[kinds == "PUT"]
    if calls.empty or puts.empty:
        return None
    call_iv, call_strike = _at_delta(calls, 0.25)
    put_iv, put_strike = _at_delta(puts, -0.25)
    return RiskReversalResult(call_iv - put_iv, call_iv, put_iv, call_strike, put_strike)
