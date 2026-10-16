"""Vol regime scatter chart: ATM IV and risk reversal percentiles."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_vol_regime_chart(data: pd.DataFrame) -> go.Figure:
    """Build a 2D scatter of tickers by IV percentile (x) vs RR percentile (y).

    Parameters
    ----------
    data:
        DataFrame with columns: ``symbol``, ``iv_rank``, ``rr_rank``.
        Optional columns: ``current_iv``, ``current_rr``, ``sample_date``,
        ``expiration_date``, ``actual_dte``.
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
        "ATM IV percentile: %{x:.0f}%",
        "25Δ RR percentile: %{y:.0f}%",
    ]
    hover_fields = [
        ("current_iv", "ATM IV: %{customdata[IDX]:.1f}%"),
        ("current_rr", "25Δ RR: %{customdata[IDX]:.2f} pp"),
        ("sample_date", "Sample: %{customdata[IDX]}"),
        ("expiration_date", "Expiration: %{customdata[IDX]}"),
        ("actual_dte", "Actual DTE: %{customdata[IDX]}"),
    ]
    present_fields = [field for field, _ in hover_fields if field in data.columns]
    for field, template in hover_fields:
        if field in present_fields:
            hover_parts.append(template.replace("IDX", str(present_fields.index(field))))

    customdata = None
    if present_fields:
        hover_data = data[present_fields].copy()
        for field in ("sample_date", "expiration_date"):
            if field in hover_data:
                hover_data[field] = hover_data[field].astype(str)
        customdata = hover_data.to_numpy()

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
        xaxis_title="ATM IV percentile vs own history  →",
        yaxis_title="25Δ RR percentile vs own history  →",
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
        (0, 50, 50, 100, "rgba(0,180,140,0.07)"),
        (50, 50, 100, 100, "rgba(180,60,80,0.07)"),
        (0, 0, 50, 50, "rgba(0,140,180,0.07)"),
        (50, 0, 100, 50, "rgba(180,100,0,0.07)"),
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
    """Add corner annotations with trade ideas on hover."""
    labels = [
        (
            0.02, 0.98, "Low IV percentile<br>High RR percentile ⓘ", "left", "top",
            "Calls are relatively rich, but overall IV is low.<br>"
            "Bearish: consider buying puts or put spreads.<br>"
            "Bullish: a call spread limits what you pay for calls.",
        ),
        (
            0.98, 0.98, "High IV percentile<br>High RR percentile ⓘ", "right", "top",
            "Overall IV is high and calls are relatively rich.<br>"
            "Fading upside: consider selling a call spread.<br>"
            "Bullish: a call spread limits the cost of rich calls.",
        ),
        (
            0.02, 0.02, "Low IV percentile<br>Low RR percentile ⓘ", "left", "bottom",
            "Overall IV is low and puts are relatively rich.<br>"
            "Bullish: consider buying calls or call spreads.<br>"
            "Willing to own lower: consider selling a put spread.",
        ),
        (
            0.98, 0.02, "High IV percentile<br>Low RR percentile ⓘ", "right", "bottom",
            "Overall IV is high and puts are relatively rich.<br>"
            "Bullish or expecting calm: sell a put credit spread.<br>"
            "Sell the higher-strike put, buy the lower-strike put; collect premium.<br>"
            "Bearish: buy a put debit spread.<br>"
            "Buy the higher-strike put, sell the lower-strike put; reduce cost, cap payoff.",
        ),
    ]
    for x, y, label, xanchor, yanchor, tip in labels:
        fig.add_annotation(
            x=x,
            y=y,
            xref="paper",
            yref="paper",
            text=label,
            hovertext=tip,
            hoverlabel={"bgcolor": "rgba(35,35,50,0.95)", "font_size": 12},
            showarrow=False,
            font={"size": 11, "color": "rgba(200,200,200,0.5)"},
            xanchor=xanchor,
            yanchor=yanchor,
        )
