"""Current 30-DTE skew against its historical moneyness-aligned range."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from options_monitor.calc.vol_skew_history import historical_band


def build_vol_skew_history_chart(
    current_points: list[tuple[float, float]],
    historical_curves: list[list[tuple[float, float]]],
    spot: float,
    strike_range_pct: float,
    symbol: str,
    lookback_days: int,
) -> go.Figure:
    """Plot current IV by strike, with 10th–90th historical IV and median."""
    width = strike_range_pct / 100
    grid = np.linspace(-width, width, 121)
    lower, median, upper, counts = historical_band(historical_curves, grid)
    strikes = spot * (1 + grid)
    fig = go.Figure()
    if np.isfinite(lower).any():
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=lower,
                mode="lines",
                line={"color": "rgba(31,178,163,0.15)", "width": 1},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=upper,
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(31,178,163,0.22)",
                line={"color": "rgba(31,178,163,0.15)", "width": 1},
                name="Historical 10th–90th percentile",
                customdata=counts,
                hovertemplate=(
                    "Strike %{x:,.0f}<br>90th IV %{y:.2f}%<br>Sessions %{customdata}<extra></extra>"
                ),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=median,
                mode="lines",
                line={"color": "#80b6af", "width": 1.5, "dash": "dash"},
                name="Historical median",
                hovertemplate="Strike %{x:,.0f}<br>Median IV %{y:.2f}%<extra></extra>",
            )
        )
    current = sorted((m, iv) for m, iv in current_points if -width <= m <= width)
    if current:
        fig.add_trace(
            go.Scatter(
                x=[spot * (1 + m) for m, _ in current],
                y=[iv for _, iv in current],
                mode="lines",
                line={"color": "#00d2c1", "width": 3},
                name="Latest chain",
                hovertemplate="Strike %{x:,.0f}<br>IV %{y:.2f}%<extra></extra>",
            )
        )
    fig.add_vline(
        x=spot,
        line_color="rgba(0,210,193,0.55)",
        line_dash="dash",
        annotation_text=f"Spot {spot:,.2f}",
        annotation_position="top right",
    )
    fig.update_layout(
        title=f"{symbol} · 30 DTE skew · {lookback_days}-day history",
        template="plotly_dark",
        height=560,
        font={"color": "#dce5ed"},
        xaxis={
            "title": "Strike (historical curves aligned by spot-relative strike)",
            "tickformat": ",.0f",
            "gridcolor": "rgba(220,229,237,0.13)",
            "zeroline": False,
        },
        yaxis={
            "title": "Implied volatility (%)",
            "ticksuffix": "%",
            "gridcolor": "rgba(220,229,237,0.13)",
            "zeroline": False,
        },
        legend={"orientation": "h", "y": 1.08, "font": {"color": "#dce5ed"}},
        margin={"l": 50, "r": 30, "t": 90, "b": 60},
        paper_bgcolor="rgba(20,20,30,1)",
        plot_bgcolor="rgba(20,20,30,1)",
        hovermode="x unified",
    )
    return fig
