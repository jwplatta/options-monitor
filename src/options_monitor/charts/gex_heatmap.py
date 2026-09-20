"""GEX time-series contour chart: top strikes by gamma exposure vs timestamp."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go

from options_monitor.data.options import load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")

_COLORSCALE = [
    [0.0, "rgb(220,0,0)"],
    [0.35, "rgb(100,0,0)"],
    [0.47, "rgb(30,10,10)"],
    [0.5, "rgb(10,10,10)"],
    [0.53, "rgb(10,30,10)"],
    [0.65, "rgb(0,100,0)"],
    [1.0, "rgb(0,220,0)"],
]


def _load_and_prep(path: Path, spot: float, strike_range: float) -> pd.DataFrame | None:
    """Load snapshot and return rows within strike range with numeric columns coerced."""
    df = load_options_snapshot(path).copy()
    df["gamma"] = pd.to_numeric(df["gamma"], errors="coerce")
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df["K"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["gamma", "open_interest", "K", "contract_type"])
    df = df[df["open_interest"] > 0]
    df = df[(df["K"] >= spot - strike_range) & (df["K"] <= spot + strike_range)]
    return df if not df.empty else None


def compute_gex_history(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    strike_range: float,
    top_n: int = 25,
) -> tuple[list[float], list[datetime], list[list[float]]]:
    """Heavy computation: returns (top_strikes, timestamps, matrix).

    Intended to be called once and stored in st.session_state. Separating this
    from figure construction means the slider can rebuild the figure instantly
    without re-running the pandas work.
    """
    # Pass 1: rank strikes by average |gamma × OI|
    gex_mag_accum: dict[float, list[float]] = {}
    for _, path in snapshots:
        df = _load_and_prep(path, spot, strike_range)
        if df is None:
            continue
        df["gex_mag"] = df["gamma"].abs() * df["open_interest"]
        for strike, mag in df.groupby("K")["gex_mag"].sum().items():
            gex_mag_accum.setdefault(float(strike), []).append(float(mag))  # type: ignore[arg-type]

    if not gex_mag_accum:
        return [], [], []

    avg_gex_mag = {k: sum(v) / len(v) for k, v in gex_mag_accum.items()}
    top_strikes = sorted(sorted(avg_gex_mag, key=lambda k: avg_gex_mag[k], reverse=True)[:top_n])
    top_set = set(top_strikes)

    # Pass 2: net GEX for top strikes at each timestamp
    time_series: dict[datetime, dict[float, float]] = {}
    for ts, path in snapshots:
        df = _load_and_prep(path, spot, strike_range)
        if df is None:
            continue
        df = df[df["K"].isin(top_set)]
        sign = df["contract_type"].str.upper().map({"CALL": 1.0, "PUT": -1.0})
        df = df.assign(gex=df["gamma"] * df["open_interest"] * (spot**2) * sign)
        df = df.dropna(subset=["gex"])
        time_series[ts] = {float(k): float(v) for k, v in df.groupby("K")["gex"].sum().items()}

    utc_timestamps = sorted(time_series.keys())
    # Convert naive UTC → naive CST/CDT (strips tz after conversion for Streamlit compat)
    timestamps = [
        ts.replace(tzinfo=UTC).astimezone(_CHICAGO).replace(tzinfo=None) for ts in utc_timestamps
    ]
    matrix = [[time_series[ts].get(strike, 0.0) for ts in utc_timestamps] for strike in top_strikes]
    return top_strikes, timestamps, matrix


# NOTE: unused — superseded by the GEX bar chart in the GEX tab
def build_gex_heatmap_chart(
    top_strikes: list[float],
    timestamps: list[datetime],
    matrix: list[list[float]],
    spot: float,
    title: str = "GEX Heatmap",
    x_range: tuple[datetime, datetime] | None = None,
) -> go.Figure:
    """Build contour figure from precomputed matrix. Fast — no data loading or pandas work.

    x_range: optional (start, end) to restrict the visible x-axis window.
    """
    if not top_strikes or not timestamps:
        fig = go.Figure()
        fig.update_layout(title=title, template="plotly_dark")
        return fig

    fig = go.Figure(
        go.Contour(
            x=timestamps,
            y=top_strikes,
            z=matrix,
            zmid=0,
            colorscale=_COLORSCALE,
            contours_coloring="heatmap",
            line_smoothing=1.3,
            ncontours=20,
            colorbar={"title": "Net GEX"},
            hovertemplate="Time: %{x}<br>Strike: %{y}<br>Net GEX: %{z:.2e}<extra></extra>",
        )
    )
    fig.add_hline(
        y=spot,
        line_dash="dash",
        line_color="white",
        annotation_text=f"Spot {spot:.0f}",
        annotation_position="right",
    )
    xaxis_kwargs: dict = {}
    if x_range is not None:
        xaxis_kwargs["range"] = list(x_range)
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Strike",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis=xaxis_kwargs,
    )
    return fig
