"""ES volume chart with session VWAP + bands and weekly VWAP."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from tractatus.calc.ma import vwap_session, vwap_weekly

_INTRADAY_FREQS = {"1min", "5min", "30min"}

# Band fill: semi-transparent magenta
_BAND_FILL = "rgba(255, 0, 255, 0.18)"
_BAND_LINE = "rgba(255, 0, 255, 0.7)"


def _day_boundary_ticks(datetimes: pd.Series) -> tuple[list[int], list[str]]:
    """One tick per trading day for integer-index intraday charts."""
    dates = datetimes.dt.normalize()
    changed = pd.Series([True], index=[dates.index[0]]).reindex(dates.index, fill_value=False)
    changed |= dates != dates.shift(1)
    tick_vals = changed[changed].index.tolist()
    tick_text = dates[changed].dt.strftime("%-m/%-d").tolist()
    return tick_vals, tick_text


# NOTE: unused — not wired into any tab
def build_sma_volume_chart(
    candles: pd.DataFrame,
    title: str = "ES Volume",
    freq: str = "day",
) -> go.Figure:
    """Bar chart: ES volume bars, close price, session VWAP with ±1σ bands, weekly VWAP."""
    intraday = freq in _INTRADAY_FREQS

    s_vwap = s_std = pd.Series(dtype=float)
    if intraday:
        s_vwap, s_std = vwap_session(candles)
    w_vwap, _ = vwap_weekly(candles)

    if intraday:
        x = list(range(len(candles)))
        tick_vals, tick_text = _day_boundary_ticks(candles["datetime"])
        hover_labels = candles["datetime"].dt.strftime("%m/%d %H:%M").tolist()
        price_hover = "%{text}<br>%{y:.2f}<extra></extra>"
        vol_hover = "%{text}<br>%{y:,.0f}<extra></extra>"
    else:
        x = candles["datetime"]  # type: ignore[assignment]
        hover_labels = None
        price_hover = None
        vol_hover = None

    fig = go.Figure()

    # ── Volume (left axis) ────────────────────────────────────────────────────
    fig.add_trace(
        go.Bar(
            x=x,
            y=candles["volume"],
            name="ES Volume",
            marker_color="steelblue",
            opacity=0.8,
            width=0.9 if intraday else None,
            yaxis="y",
            text=hover_labels,
            hovertemplate=vol_hover,
        )
    )

    # ── Price / VWAP (right axis) ─────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=x,
            y=candles["close"],
            name="ES",
            line={"color": "white", "width": 1},
            opacity=0.7,
            yaxis="y2",
            text=hover_labels,
            hovertemplate=price_hover,
        )
    )

    if intraday:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=s_vwap + s_std,
                name="VWAP ±1σ",
                line={"color": _BAND_LINE, "width": 1.0, "dash": "dot"},
                yaxis="y2",
                showlegend=True,
                text=hover_labels,
                hovertemplate=price_hover,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=s_vwap - s_std,
                name="VWAP −1σ",
                line={"color": _BAND_LINE, "width": 1.0, "dash": "dot"},
                fill="tonexty",
                fillcolor=_BAND_FILL,
                yaxis="y2",
                showlegend=False,
                text=hover_labels,
                hovertemplate=price_hover,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=s_vwap,
                name="Session VWAP",
                line={"color": "magenta", "width": 1.5},
                yaxis="y2",
                text=hover_labels,
                hovertemplate=price_hover,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=x,
            y=w_vwap,
            name="Weekly VWAP",
            line={"color": "gold", "width": 1.5, "dash": "dash"},
            yaxis="y2",
            text=hover_labels,
            hovertemplate=price_hover,
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Date/Time",
        yaxis={"title": "Volume"},
        yaxis2={"title": "Price", "overlaying": "y", "side": "right", "showgrid": False},
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 60, "t": 40, "b": 40},
        bargap=0,
    )
    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)
    return fig
