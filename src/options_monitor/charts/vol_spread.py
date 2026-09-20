"""IV-RV spread chart: 3 lines on one figure."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def _rangebreaks(freq: str) -> list[dict[str, object]]:
    """Plotly rangebreaks to hide weekends and (for intraday) overnight gaps."""
    breaks: list[dict[str, object]] = [{"bounds": ["sat", "mon"]}]
    if freq != "day":
        # UTC: market closes 21:00, opens 14:30
        breaks.append({"bounds": [21, 14.5], "pattern": "hour"})
    return breaks


def _tickformat(freq: str) -> str:
    return "%Y-%m-%d" if freq == "day" else "%m/%d %H:%M"


def build_iv_rv_chart(
    iv: pd.Series[float],
    rv: pd.Series[float],
    spread: pd.Series[float],
    datetimes: pd.Series[pd.Timestamp],
    window_label: str = "30D",
    freq: str = "day",
) -> go.Figure:
    """Three-line chart: IV (VIX/VIX9D), Realized Vol, and IV-RV spread."""
    if not (len(iv) == len(rv) == len(spread) == len(datetimes)):
        raise ValueError("iv, rv, spread, and datetimes must all have the same length")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=datetimes,
            y=iv,
            name=f"IV ({window_label})",
            line={"color": "cyan", "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=datetimes,
            y=rv,
            name=f"Realized Vol ({window_label})",
            line={"color": "orange", "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=datetimes,
            y=spread,
            name="IV − RV Spread",
            line={"color": "yellow", "width": 1.5, "dash": "dot"},
        )
    )
    fig.add_hline(y=0, line_color="white", line_width=0.5)
    fig.update_layout(
        title=f"IV vs Realized Volatility ({window_label})",
        xaxis_title="Date" if freq == "day" else "Date / Time",
        yaxis_title="Volatility (%)",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis={
            "rangebreaks": _rangebreaks(freq),
            "tickformat": _tickformat(freq),
        },
    )
    return fig
