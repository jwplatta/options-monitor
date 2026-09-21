"""Vol regime scatter chart: IV rank vs Risk Reversal rank (percentiles)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_vol_regime_chart(data: pd.DataFrame) -> go.Figure:
    """Build a 2D scatter of tickers by IV rank (x) vs RR rank (y).

    Parameters
    ----------
    data:
        DataFrame with columns: ``symbol``, ``iv_rank``, ``rr_rank``.
        Optional columns: ``current_iv``, ``current_rr``.
    """
    fig = go.Figure()

    # Quadrant background shading (midpoint at 50)
    _add_quadrant_shading(fig)

    # Crosshairs at 50
    fig.add_hline(y=50, line_color="rgba(255,255,255,0.3)", line_width=1)
    fig.add_vline(x=50, line_color="rgba(255,255,255,0.3)", line_width=1)

    # Scatter points
    hover_parts = [
        "<b>%{text}</b>",
        "IV Rank: %{x:.0f}%",
        "RR Rank: %{y:.0f}%",
    ]
    if "current_iv" in data.columns:
        hover_parts.append("IV: %{customdata[0]:.1f}%")
    if "current_rr" in data.columns:
        hover_parts.append("RR: %{customdata[1]:.2f}%")

    customdata = None
    if {"current_iv", "current_rr"}.issubset(data.columns):
        customdata = data[["current_iv", "current_rr"]].values

    fig.add_trace(
        go.Scatter(
            x=data["iv_rank"],
            y=data["rr_rank"],
            mode="markers+text",
            text=data["symbol"],
            textposition="top center",
            textfont={"size": 11, "color": "rgba(220,220,255,0.9)"},
            marker={
                "size": 10,
                "color": "rgba(160,140,255,0.8)",
                "line": {"width": 1, "color": "rgba(255,255,255,0.4)"},
            },
            customdata=customdata,
            hovertemplate="<br>".join(hover_parts) + "<extra></extra>",
        )
    )

    # Quadrant labels
    _add_quadrant_labels(fig)

    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin={"l": 60, "r": 60, "t": 40, "b": 60},
        xaxis_title="IV Rank  →  High IV Rank",
        yaxis_title="RR Rank  →  Calls Rich (Upside Bid)",
        xaxis={"range": [-2, 102]},
        yaxis={"range": [-2, 102]},
        paper_bgcolor="rgba(20,20,30,1)",
        plot_bgcolor="rgba(20,20,30,1)",
        showlegend=False,
    )

    return fig


def _add_quadrant_shading(fig: go.Figure) -> None:
    """Add translucent quadrant fills (split at 50)."""
    quads = [
        # (x0, y0, x1, y1, color)
        (0, 50, 50, 100, "rgba(0,180,140,0.07)"),  # top-left: cheap vol, upside
        (50, 50, 100, 100, "rgba(180,60,80,0.07)"),  # top-right: expensive vol, upside
        (0, 0, 50, 50, "rgba(0,140,180,0.07)"),  # bottom-left: cheap vol, downside
        (50, 0, 100, 50, "rgba(180,100,0,0.07)"),  # bottom-right: expensive vol, downside
    ]
    for x0, y0, x1, y1, color in quads:
        fig.add_shape(
            type="rect",
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            fillcolor=color,
            line_width=0,
            layer="below",
        )


def _add_quadrant_labels(fig: go.Figure) -> None:
    """Add corner annotations for each quadrant."""
    labels = [
        (0.02, 0.98, "Cheap Vol<br>Upside Potential", "left", "top"),
        (0.98, 0.98, "Expensive Vol<br>Upside Potential", "right", "top"),
        (0.02, 0.02, "Cheap Vol<br>Downside Potential", "left", "bottom"),
        (0.98, 0.02, "Expensive Vol<br>Downside Potential", "right", "bottom"),
    ]
    for x, y, text, xanchor, yanchor in labels:
        fig.add_annotation(
            x=x,
            y=y,
            xref="paper",
            yref="paper",
            text=text,
            showarrow=False,
            font={"size": 11, "color": "rgba(200,200,200,0.5)"},
            xanchor=xanchor,
            yanchor=yanchor,
        )
