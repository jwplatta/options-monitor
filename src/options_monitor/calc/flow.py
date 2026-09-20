"""Intraday options flow metric: normalized volume delta × signed delta."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from options_monitor.data.options import load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


def compute_intraday_flow(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    moneyness_pct: float = 0.15,
    contract_filter: str = "ALL",
    bucket_minutes: int = 5,
    weight_by_delta: bool = True,
    target_date: date | None = None,
    preloaded: pd.DataFrame | None = None,
) -> tuple[list[float], list[datetime], list[list[float]], list[float]]:
    """Compute intraday flow matrix for a heatmap.

    For each contract (strike x expiry x type), computes:
        dV           = total_volume.diff() per snapshot interval
        z            = (dV - mean_dV_strike) / std_dV_strike
        signed_delta = delta clipped to ±0.75
        flow         = z * signed_delta

    Returns (strikes, timestamps, matrix, prices) where matrix[i][j] is the
    flow value for strikes[i] at timestamps[j], and prices[j] is the
    underlying_price at timestamps[j]. Only snapshots matching `target_date`
    (defaults to today) are included.
    preloaded: if provided, used instead of loading from snapshot paths (historical parquet path).
    """
    if not snapshots and preloaded is None:
        return [], [], [], []

    price_by_ts: dict[Any, float] = {}

    if preloaded is not None:
        combined = preloaded.copy()
        # Build price_by_ts from the preloaded data
        for ts_val, grp in combined.groupby("_ts"):
            price_val = pd.to_numeric(grp["underlying_price"], errors="coerce").dropna()
            if not price_val.empty:
                price_by_ts[ts_val] = float(price_val.iloc[0])
    else:
        local_target_date = target_date if target_date is not None else date.today()

        # Filter to the selected Chicago-local session date and downsample.
        today_snapshots = sorted(
            ((ts, path) for ts, path in snapshots if _to_chicago(ts).date() == local_target_date),
            key=lambda x: x[0],
        )
        seen_buckets: set[datetime] = set()
        sampled: list[tuple[datetime, Path]] = []
        for ts, path in today_snapshots:
            floored = (ts.minute // bucket_minutes) * bucket_minutes
            bucket = ts.replace(minute=floored, second=0, microsecond=0)
            if bucket not in seen_buckets:
                seen_buckets.add(bucket)
                sampled.append((ts, path))

        # Load sampled snapshots, tag each row with its timestamp
        # Also capture one underlying_price per timestamp for the price overlay
        frames: list[pd.DataFrame] = []
        for ts, path in sampled:
            df = load_options_snapshot(path).copy()
            df["_ts"] = ts
            frames.append(df)
            price_val = pd.to_numeric(df["underlying_price"], errors="coerce").dropna()
            if not price_val.empty:
                price_by_ts[ts] = float(price_val.iloc[0])

        if not frames:
            return [], [], [], []

        combined = pd.concat(frames, ignore_index=True)

    # Drop rows with no volume
    combined = combined[combined["total_volume"] > 0]

    # Moneyness filter
    combined["_strike"] = pd.to_numeric(combined["strike"], errors="coerce")
    combined = combined.dropna(subset=["_strike"])
    combined = combined[(combined["_strike"] - spot).abs() / spot <= moneyness_pct]

    if combined.empty:
        return [], [], [], []

    # Contract type filter
    if contract_filter != "ALL":
        combined = combined[combined["contract_type"].str.upper() == contract_filter]

    if combined.empty:
        return [], [], [], []

    # Coerce numeric columns
    for col in ["total_volume", "delta"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined.dropna(subset=["total_volume", "delta", "contract_type"])

    # Compute flow per contract group
    contract_cols = ["_strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(["_strike", "expiration_date", "contract_type", "_ts"])

    flow_rows: list[dict[str, object]] = []
    for _, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts").copy()
        if len(grp) < 2:
            continue

        dV = grp["total_volume"].diff()
        dV_inner = dV.iloc[1:]
        std = dV_inner.std()
        if std == 0 or pd.isna(std):
            continue
        z = (dV_inner - dV_inner.mean()) / std
        sign = grp["contract_type"].iloc[1:].str.upper().map({"CALL": 1.0, "PUT": -1.0}).fillna(1.0)
        signed_delta = grp["delta"].iloc[1:].clip(-0.65, 0.65) * sign

        flow = z * signed_delta if weight_by_delta else z

        for ts_val, flow_val, strike_val in zip(
            grp["_ts"].iloc[1:], flow, grp["_strike"].iloc[1:], strict=True
        ):
            if pd.isna(flow_val):
                continue
            flow_rows.append({"_ts": ts_val, "_strike": float(strike_val), "flow": float(flow_val)})

    if not flow_rows:
        return [], [], [], []

    flow_df = pd.DataFrame(flow_rows)

    # Aggregate duplicate (strike, ts) cells by mean
    flow_df = flow_df.groupby(["_strike", "_ts"], as_index=False)["flow"].mean()  # type: ignore[assignment]

    # Pivot to matrix
    pivot = flow_df.pivot(index="_strike", columns="_ts", values="flow").fillna(0.0)
    pivot = pivot.sort_index()

    strikes = [float(s) for s in pivot.index]
    utc_timestamps = list(pivot.columns)

    # Convert UTC - Chicago naive (matches gex_heatmap.py convention)
    timestamps = [_to_chicago(ts) for ts in utc_timestamps]  # type: ignore[arg-type]

    matrix = pivot.values.tolist()
    prices = [price_by_ts.get(ts, float("nan")) for ts in utc_timestamps]
    return strikes, timestamps, matrix, prices
