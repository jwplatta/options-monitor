"""Price charts: SMA line chart and candlestick chart."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tractatus.calc.ma import sma, validate_windows

from options_monitor.charts._chart_utils import daily_ticks as _daily_ticks
from options_monitor.charts._chart_utils import intraday_ticks as _intraday_ticks
from options_monitor.charts._chart_utils import to_ct as _to_ct

_INTRADAY_FREQS = {"1min", "5min", "30min"}


# NOTE: unused — not wired into any tab
def build_sma_price_chart(
    candles: pd.DataFrame,
    fast_window: int,
    slow_window: int,
    title: str = "Price with Moving Averages",
    freq: str = "day",
) -> go.Figure:
    """Line chart: close + fast MA + slow MA. Raises ValueError if windows invalid."""
    validate_windows(fast=fast_window, slow=slow_window)
    fast_ma = sma(candles["close"], window=fast_window)
    slow_ma = sma(candles["close"], window=slow_window)

    intraday = freq in _INTRADAY_FREQS
    if intraday:
        x = list(range(len(candles)))
        tick_vals, tick_text = _intraday_ticks(candles["datetime"], freq)
        hover_labels = candles["datetime"].dt.strftime("%m/%d %H:%M").tolist()
        hover_tmpl = "%{text}<br>%{y:.2f}<extra></extra>"
    else:
        x = candles["datetime"]  # type: ignore[assignment]
        hover_labels = None
        hover_tmpl = None

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=candles["close"],
            name="Close",
            line={"color": "white", "width": 1},
            opacity=0.7,
            text=hover_labels,
            hovertemplate=hover_tmpl,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=fast_ma,
            name=f"Fast MA ({fast_window})",
            line={"color": "orange", "width": 1.5},
            text=hover_labels,
            hovertemplate=hover_tmpl,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=slow_ma,
            name=f"Slow MA ({slow_window})",
            line={"color": "cyan", "width": 1.5},
            text=hover_labels,
            hovertemplate=hover_tmpl,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Date/Time",
        yaxis_title="Price",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)
    return fig


# NOTE: unused — not wired into any tab
def build_candlestick_chart(
    candles: pd.DataFrame,
    title: str = "Candlestick",
    freq: str = "day",
    raw_call_wall: float | None = None,
    raw_put_wall: float | None = None,
    dw_call_wall: float | None = None,
    dw_put_wall: float | None = None,
    cluster_call_wall: float | None = None,
    cluster_put_wall: float | None = None,
    zero_gamma: float | None = None,
) -> go.Figure:
    """Candlestick chart. Optionally overlays GEX wall and zero-gamma horizontal lines."""
    intraday = freq in _INTRADAY_FREQS
    if intraday:
        x = list(range(len(candles)))
        tick_vals, tick_text = _intraday_ticks(candles["datetime"], freq)
        hover_labels = _to_ct(candles["datetime"]).dt.strftime("%m/%d %H:%M CT").tolist()
        hover_tmpl = "%{text}<extra></extra>"
    else:
        x = candles["datetime"]  # type: ignore[assignment]
        tick_vals_daily, tick_text_daily = _daily_ticks(candles["datetime"])
        hover_labels = None
        hover_tmpl = None

    has_volume = "volume" in candles.columns and candles["volume"].notna().any()

    if has_volume:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.65, 0.35],
            vertical_spacing=0.02,
        )
    else:
        fig = make_subplots(rows=1, cols=1)

    fig.add_trace(
        go.Candlestick(
            x=x,
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            text=hover_labels,
            hovertemplate=hover_tmpl,
            increasing_line_color="limegreen",
            decreasing_line_color="tomato",
        ),
        row=1,
        col=1,
    )

    if has_volume:
        fig.add_trace(
            go.Bar(
                x=x,
                y=candles["volume"],
                marker_color="steelblue",
                opacity=0.7,
                showlegend=False,
                hoverinfo="skip",
            ),
            row=2,
            col=1,
        )

    _WALL_LINES: list[tuple[float | None, str, str, str]] = [
        (raw_call_wall, f"CW {raw_call_wall}", "limegreen", "solid"),
        (raw_put_wall, f"PW {raw_put_wall}", "tomato", "solid"),
        (dw_call_wall, f"CW-DW {dw_call_wall}", "mediumseagreen", "dash"),
        (dw_put_wall, f"PW-DW {dw_put_wall}", "indianred", "dash"),
        (cluster_call_wall, f"CW-CL {cluster_call_wall}", "darkseagreen", "dot"),
        (cluster_put_wall, f"PW-CL {cluster_put_wall}", "lightcoral", "dot"),
        (zero_gamma, f"ZGL {zero_gamma}", "gold", "dot"),
    ]
    for level, label, color, dash in _WALL_LINES:
        if level is not None:
            fig.add_hline(
                y=level,
                line={"color": color, "width": 1, "dash": dash},
                annotation_text=label,
                annotation_position="right",
                annotation_font_color=color,
                row=1,
            )

    fig.update_layout(
        title=title,
        yaxis_title="Price",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis_rangeslider_visible=False,
    )
    if has_volume:
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_xaxes(title_text="Date/Time", row=2, col=1)
    else:
        fig.update_xaxes(title_text="Date/Time", row=1, col=1)
    if intraday:
        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickangle=-45)
    else:
        fig.update_xaxes(tickvals=tick_vals_daily, ticktext=tick_text_daily, tickangle=-45)
    return fig
