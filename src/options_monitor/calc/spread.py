"""Intraday bid-ask spread z-score: rolling 10-period normalized spread per contract."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from options_monitor.data.options import load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


# NOTE: unused — planned feature, not yet wired into any tab
def compute_intraday_spread(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    moneyness_pct: float = 0.15,
    contract_filter: str = "CALL",
    bucket_minutes: int = 5,
    target_date: date | None = None,
) -> tuple[list[float], list[datetime], list[list[float]], list[float]]:
    """Compute intraday bid-ask spread z-score matrix for a heatmap.

    For each contract (strike x expiry x type), computes:
        spread       = ask - bid
        rolling_mean = spread.rolling(10, min_periods=2).mean()
        rolling_std  = spread.rolling(10, min_periods=2).std()
        z_score      = (spread - rolling_mean) / rolling_std

    contract_filter must be "CALL" or "PUT" (no "ALL").

    Returns (strikes, timestamps, matrix, prices) where matrix[i][j] is the
    spread z-score for strikes[i] at timestamps[j], and prices[j] is the
    underlying_price at timestamps[j].
    """
    if not snapshots:
        return [], [], [], []

    local_target_date = target_date if target_date is not None else date.today()

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

    frames: list[pd.DataFrame] = []
    price_by_ts: dict[datetime, float] = {}
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

    # Coerce bid/ask and drop rows missing either
    for col in ["bid", "ask"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    combined = combined.dropna(subset=["bid", "ask"])

    # Moneyness filter
    combined["_strike"] = pd.to_numeric(combined["strike"], errors="coerce")
    combined = combined.dropna(subset=["_strike"])
    combined = combined[(combined["_strike"] - spot).abs() / spot <= moneyness_pct]

    if combined.empty:
        return [], [], [], []

    combined = combined[combined["contract_type"].str.upper() == contract_filter.upper()]

    if combined.empty:
        return [], [], [], []

    # Compute spread z-score per contract group
    contract_cols = ["_strike", "expiration_date", "contract_type"]
    combined = combined.sort_values(["_strike", "expiration_date", "contract_type", "_ts"])

    spread_rows: list[dict[str, object]] = []
    for _, grp in combined.groupby(contract_cols, sort=False):
        grp = grp.sort_values("_ts").copy()
        if len(grp) < 2:
            continue

        spread = grp["ask"] - grp["bid"]
        rolling_mean = spread.rolling(10, min_periods=2).mean()
        rolling_std = spread.rolling(10, min_periods=2).std()

        valid = rolling_std > 0
        z_score = (spread - rolling_mean) / rolling_std.where(valid)

        for ts_val, z_val, strike_val in zip(grp["_ts"], z_score, grp["_strike"], strict=True):
            if pd.isna(z_val):
                continue
            spread_rows.append({"_ts": ts_val, "_strike": float(strike_val), "z": float(z_val)})

    if not spread_rows:
        return [], [], [], []

    spread_df = pd.DataFrame(spread_rows)

    spread_df = spread_df.groupby(["_strike", "_ts"], as_index=False)["z"].mean()  # type: ignore[assignment]

    pivot = spread_df.pivot(index="_strike", columns="_ts", values="z").fillna(0.0)
    pivot = pivot.sort_index()

    strikes = [float(s) for s in pivot.index]
    utc_timestamps = list(pivot.columns)

    timestamps = [_to_chicago(ts) for ts in utc_timestamps]  # type: ignore[arg-type]

    matrix = pivot.values.tolist()
    prices = [price_by_ts.get(ts, float("nan")) for ts in utc_timestamps]  # type: ignore[call-overload]
    return strikes, timestamps, matrix, prices
