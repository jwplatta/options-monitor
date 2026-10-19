"""Comparable OTM volatility skews and historical bands."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd


def otm_skew_points(snapshot: pd.DataFrame, spot: float) -> list[tuple[float, float]]:
    """Return (strike/spot - 1, IV percent) using puts below spot and calls above."""
    if spot <= 0 or not {"strike", "volatility", "contract_type"}.issubset(snapshot):
        return []
    df = snapshot[["strike", "volatility", "contract_type"]].copy()
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["volatility"] = pd.to_numeric(df["volatility"], errors="coerce")
    df["contract_type"] = df["contract_type"].astype(str).str.upper()
    df = df.dropna(subset=["strike", "volatility"])
    df = df[(df["strike"] > 0) & (df["volatility"] > 0)]
    df = df[
        ((df["strike"] < spot) & (df["contract_type"] == "PUT"))
        | ((df["strike"] > spot) & (df["contract_type"] == "CALL"))
        | ((df["strike"] == spot) & df["contract_type"].isin(["PUT", "CALL"]))
    ]
    grouped = df.groupby("strike")["volatility"].mean().sort_index()
    return [(cast(float, strike) / spot - 1, float(iv)) for strike, iv in grouped.items()]


def historical_band(
    curves: list[list[tuple[float, float]]],
    grid: np.ndarray,
    min_curves: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate each daily curve in moneyness; never extrapolate its wings."""
    rows: list[np.ndarray] = []
    for points in curves:
        if len(points) < 2:
            continue
        x, y = np.array(sorted(points), dtype=float).T
        if len(np.unique(x)) < 2:
            continue
        interpolated = np.interp(grid, x, y)
        interpolated[(grid < x[0]) | (grid > x[-1])] = np.nan
        rows.append(interpolated)
    lower = np.full(len(grid), np.nan)
    median = np.full(len(grid), np.nan)
    upper = np.full(len(grid), np.nan)
    counts = np.zeros(len(grid), dtype=int)
    if not rows:
        return lower, median, upper, counts
    matrix = np.vstack(rows)
    for i in range(len(grid)):
        values = matrix[:, i]
        values = values[np.isfinite(values)]
        counts[i] = len(values)
        if len(values) >= min_curves:
            lower[i], median[i], upper[i] = np.percentile(values, [10, 50, 90])
    return lower, median, upper, counts
