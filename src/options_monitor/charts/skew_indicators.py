"""Compact indicator row for vol skew scalar metrics."""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tractatus.calc.vol import RiskReversalResult

_GREEN = "#00c46a"
_RED = "#ef5350"
_NEUTRAL = "#b0bec5"


def build_skew_indicators(
    rr: RiskReversalResult,
    spot: float | None = None,
    title: str = "",
) -> go.Figure:
    """One-row Plotly indicator figure showing 25-delta risk reversal scalar metrics.

    Tiles (left to right):
      1. Risk Reversal value (sign-colored, number+delta mode)
      2. 25Δ Call IV  (green, with strike subtitle)
      3. 25Δ Put IV   (red, with strike subtitle)
    """
    rr_color = _GREEN if rr.rr > 0.5 else (_RED if rr.rr < -0.5 else _NEUTRAL)

    fig = make_subplots(
        rows=1,
        cols=3,
        specs=[[{"type": "indicator"}] * 3],
    )

    # Tile 1: Risk Reversal (number + delta arrow relative to zero)
    _rr_subtitle = "<span style='font-size:0.75em'>25\u0394 Call \u2212 Put IV</span>"
    fig.add_trace(
        go.Indicator(
            mode="number+delta",
            value=rr.rr,
            title={"text": f"Risk Reversal<br>{_rr_subtitle}"},
            number={"suffix": "%", "font": {"color": rr_color}, "valueformat": ".2f"},
            delta={
                "reference": 0.0,
                "valueformat": ".2f",
                "increasing": {"color": _GREEN},
                "decreasing": {"color": _RED},
            },
        ),
        row=1,
        col=1,
    )

    # Tile 2: 25D Call IV
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=rr.iv_25d_call,
            title={
                "text": (
                    f"25Δ Call IV<br>"
                    f"<span style='font-size:0.75em'>K {rr.strike_25d_call:.0f}</span>"
                )
            },
            number={"suffix": "%", "font": {"color": _GREEN}, "valueformat": ".2f"},
        ),
        row=1,
        col=2,
    )

    # Tile 3: 25D Put IV
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=rr.iv_25d_put,
            title={
                "text": (
                    f"25Δ Put IV<br><span style='font-size:0.75em'>K {rr.strike_25d_put:.0f}</span>"
                )
            },
            number={"suffix": "%", "font": {"color": _RED}, "valueformat": ".2f"},
        ),
        row=1,
        col=3,
    )

    fig.update_layout(
        template="plotly_dark",
        height=140,
        margin={"l": 20, "r": 20, "t": 30, "b": 10},
        title_text=title,
        title_font_size=11,
    )
    return fig
