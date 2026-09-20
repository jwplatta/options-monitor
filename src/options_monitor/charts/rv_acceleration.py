"""Realized volatility acceleration chart: log returns + fast/slow RV with spread."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tractatus.calc.vol import realized_vol

_INTRADAY_FREQS = {"1min", "5min", "30min"}
_BARS_PER_DAY = {"1min": 390, "5min": 78, "30min": 13, "day": 1}


def _day_boundary_ticks(datetimes: pd.Series) -> tuple[list[int], list[str]]:
    """One tick per trading day for integer-index intraday charts."""
    dates = datetimes.dt.normalize()
    changed = pd.Series([True], index=[dates.index[0]]).reindex(dates.index, fill_value=False)
    changed |= dates != dates.shift(1)
    tick_vals = changed[changed].index.tolist()
    tick_text = dates[changed].dt.strftime("%-m/%-d").tolist()
    return tick_vals, tick_text


def build_rv_acceleration_chart(
    candles: pd.DataFrame,
    fast_days: int,
    slow_days: int,
    freq: str = "day",
    title: str = "RV Acceleration",
) -> go.Figure:
    """Two-pane chart: log returns + fast/slow RV (top) + spread bar (bottom).

    Spread > 0 (fast RV > slow RV) → volatility clustering / regime unstable.
    Spread < 0 → vol decelerating / regime stabilizing.
    """
    bars_per_day = _BARS_PER_DAY.get(freq, 1)
    ann_factor = bars_per_day * 252
    fast_window = fast_days * bars_per_day
    slow_window = slow_days * bars_per_day

    fast_rv = realized_vol(candles["close"], window=fast_window, periods_per_year=ann_factor)
    slow_rv = realized_vol(candles["close"], window=slow_window, periods_per_year=ann_factor)
    spread = fast_rv - slow_rv

    intraday = freq in _INTRADAY_FREQS
    if intraday:
        x = list(range(len(candles)))
        tick_vals, tick_text = _day_boundary_ticks(candles["datetime"])
        hover_labels = candles["datetime"].dt.strftime("%m/%d %H:%M").tolist()
        rv_hover = "%{text}<br>%{y:.1f}%<extra></extra>"
        sp_hover = "%{text}<br>%{y:.1f}%<extra></extra>"
    else:
        x = candles["datetime"].tolist()
        hover_labels = None
        rv_hover = None
        sp_hover = None

    spread_colors = [
        "rgba(220, 60, 60, 0.75)" if v >= 0 else "rgba(40, 180, 120, 0.75)"
        for v in spread.fillna(0)
    ]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        row_heights=[0.62, 0.38],
        vertical_spacing=0.04,
    )

    # ── Row 1: SPX price (left) + slow/fast RV lines (right) ────────────────
    fig.add_trace(
        go.Scatter(
            x=x,
            y=candles["close"],
            name="SPX Price",
            line={"color": "rgba(255,255,255,0.55)", "width": 1},
            text=hover_labels,
            hovertemplate="%{text}<br>%{y:,.2f}<extra></extra>" if hover_labels else None,
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=slow_rv,
            name=f"RV {slow_days}d",
            line={"color": "cyan", "width": 1.5},
            text=hover_labels,
            hovertemplate=rv_hover,
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=fast_rv,
            name=f"RV {fast_days}d",
            line={"color": "orange", "width": 1.5},
            text=hover_labels,
            hovertemplate=rv_hover,
        ),
        row=1,
        col=1,
        secondary_y=True,
    )

    # ── Row 2: spread bars (fast − slow) ─────────────────────────────────────
    fig.add_trace(
        go.Bar(
            x=x,
            y=spread,
            name=f"Spread ({fast_days}d − {slow_days}d)",
            marker_color=spread_colors,
            text=hover_labels,
            hovertemplate=sp_hover,
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=[x[0], x[-1]] if x else [],
            y=[0.0, 0.0],
            mode="lines",
            line={"color": "white", "width": 0.5},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=title,
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 60, "t": 40, "b": 40},
        bargap=0,
    )
    fig.update_yaxes(title_text="Price", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="RV (%)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Spread (pp)", row=2, col=1)
    fig.update_xaxes(title_text="Date/Time", row=2, col=1)

    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)

    return fig
