"""GEX aggregate chart: strike bars + price-grid line + spot + ZGL + all key levels."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tractatus.calc.gex import find_zero_gamma_level


def _add_vertical_marker(
    fig: go.Figure,
    x: float,
    text: str,
    color: str,
    line_dash: str,
    y_paper: float,
    xanchor: str,
) -> None:
    fig.add_vline(x=x, line_dash=line_dash, line_color=color)
    fig.add_annotation(
        x=x,
        y=y_paper,
        xref="x",
        yref="paper",
        text=text,
        textangle=-90,
        showarrow=False,
        font={"color": color},
        xanchor=xanchor,
        yanchor="middle",
        bgcolor="rgba(0, 0, 0, 0.45)",
    )


def _add_zone_overlay(
    fig: go.Figure,
    low: float,
    high: float,
    label: str,
    color: str,
    y_paper: float,
    xanchor: str,
) -> None:
    center = (low + high) / 2.0
    fig.add_vrect(
        x0=low,
        x1=high,
        fillcolor=color,
        opacity=0.12,
        line_width=1,
        line_color=color,
    )
    fig.add_annotation(
        x=center,
        y=y_paper,
        xref="x",
        yref="paper",
        text=label,
        textangle=-90,
        showarrow=False,
        font={"color": color},
        xanchor=xanchor,
        yanchor="middle",
        bgcolor="rgba(0, 0, 0, 0.45)",
    )


def build_gex_aggregate_chart(
    strike_gex: pd.DataFrame,
    price_gex: pd.DataFrame,
    spot: float,
    # SpotGamma-style raw OI×gamma peak walls
    raw_call_wall: float | None = None,
    raw_put_wall: float | None = None,
    # DTE-weighted aggregate walls
    dw_call_wall: float | None = None,
    dw_put_wall: float | None = None,
    # Per-expiry clustering walls
    cluster_call_wall: float | None = None,
    cluster_put_wall: float | None = None,
    # Decision zones (magnitude + persistence scored)
    resistance_zones: list[dict[str, float]] | None = None,
    support_zones: list[dict[str, float]] | None = None,
    title: str = "GEX Aggregate",
) -> go.Figure:
    """Mixed bar (net GEX by strike) + line (net GEX by price) + all key levels.

    Three wall models are shown simultaneously with distinct colors:
    - Raw (SpotGamma-style): brightest green/red solid lines
    - Distance-weighted aggregate: medium green/red dashed lines
    - Per-expiry clustering: muted green/red dotted lines

    Decision zones are translucent bands scored by magnitude + persistence.

    Args:
        strike_gex: DataFrame[strike, net_gex]
        price_gex: DataFrame[price, net_gex]
        spot: Current underlying price
        raw_call_wall: SpotGamma-style call wall (peak raw OI x gamma above spot)
        raw_put_wall: SpotGamma-style put wall (peak raw OI x gamma below spot)
        dw_call_wall: DTE-weighted aggregate call wall
        dw_put_wall: DTE-weighted aggregate put wall
        cluster_call_wall: Per-expiry clustering call wall
        cluster_put_wall: Per-expiry clustering put wall
        resistance_zones: [{low, high, center, score}] resistance bands
        support_zones: [{low, high, center, score}] support bands
        title: Chart title
    """
    zgl = find_zero_gamma_level(
        prices=price_gex["price"].to_numpy(dtype=float),
        gex=price_gex["net_gex"].to_numpy(dtype=float),
    )

    colors: list[str] = ["green" if g >= 0 else "red" for g in strike_gex["net_gex"]]

    max_bar = float(np.abs(strike_gex["net_gex"]).max()) or 1.0
    max_line = float(np.abs(price_gex["net_gex"]).max()) or 1.0
    scale = max_bar / max_line

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=strike_gex["strike"],
            y=strike_gex["net_gex"],
            name="Net GEX by Strike",
            marker_color=colors,
            opacity=0.7,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=price_gex["price"],
            y=price_gex["net_gex"] * scale,
            name="Net GEX by Price (scaled)",
            line={"color": "yellow", "width": 2},
        )
    )
    fig.add_hline(y=0, line_dash="solid", line_color="white", line_width=0.5)

    # --- Spot and ZGL ---
    _add_vertical_marker(
        fig,
        x=spot,
        text=f"Spot {spot:.0f}",
        color="white",
        line_dash="dash",
        y_paper=0.92,
        xanchor="left",
    )
    if zgl is not None:
        _add_vertical_marker(
            fig,
            x=zgl,
            text=f"ZGL {zgl:.0f}",
            color="yellow",
            line_dash="dot",
            y_paper=0.84,
            xanchor="right",
        )
    # --- Decision zones (translucent bands, no annotation clutter) ---
    for idx, zone in enumerate(resistance_zones or [], start=1):
        _add_zone_overlay(
            fig,
            low=float(zone["low"]),
            high=float(zone["high"]),
            label=f"R{idx} {zone['low']:.0f}–{zone['high']:.0f}",
            color="rgba(0, 220, 0, 0.9)",
            y_paper=0.20 + (idx - 1) * 0.08,
            xanchor="left",
        )
    for idx, zone in enumerate(support_zones or [], start=1):
        _add_zone_overlay(
            fig,
            low=float(zone["low"]),
            high=float(zone["high"]),
            label=f"S{idx} {zone['low']:.0f}\u2013{zone['high']:.0f}",
            color="rgba(220, 0, 0, 0.9)",
            y_paper=0.20 + (idx - 1) * 0.08,
            xanchor="right",
        )

    # --- Raw (SpotGamma-style) walls — solid, brightest, topmost labels ---
    if raw_call_wall is not None:
        _add_vertical_marker(
            fig,
            x=raw_call_wall,
            text=f"CW {raw_call_wall:.0f}",
            color="#00ff88",
            line_dash="solid",
            y_paper=0.72,
            xanchor="left",
        )
    if raw_put_wall is not None:
        _add_vertical_marker(
            fig,
            x=raw_put_wall,
            text=f"PW {raw_put_wall:.0f}",
            color="#ff4444",
            line_dash="solid",
            y_paper=0.72,
            xanchor="right",
        )

    # --- Distance-weighted aggregate walls — dashed, mid-brightness ---
    if dw_call_wall is not None:
        _add_vertical_marker(
            fig,
            x=dw_call_wall,
            text=f"CW-DW {dw_call_wall:.0f}",
            color="#00cc66",
            line_dash="dash",
            y_paper=0.60,
            xanchor="left",
        )
    if dw_put_wall is not None:
        _add_vertical_marker(
            fig,
            x=dw_put_wall,
            text=f"PW-DW {dw_put_wall:.0f}",
            color="#cc2222",
            line_dash="dash",
            y_paper=0.60,
            xanchor="right",
        )

    # --- Per-expiry clustering walls — dotted, muted ---
    if cluster_call_wall is not None:
        _add_vertical_marker(
            fig,
            x=cluster_call_wall,
            text=f"CW-CL {cluster_call_wall:.0f}",
            color="#009944",
            line_dash="dot",
            y_paper=0.48,
            xanchor="left",
        )
    if cluster_put_wall is not None:
        _add_vertical_marker(
            fig,
            x=cluster_put_wall,
            text=f"PW-CL {cluster_put_wall:.0f}",
            color="#991111",
            line_dash="dot",
            y_paper=0.48,
            xanchor="right",
        )

    fig.update_layout(
        title=title,
        xaxis_title="Strike / Price",
        xaxis={"dtick": 25},
        yaxis_title="Net GEX",
        template="plotly_dark",
        legend={"orientation": "h", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        bargap=0.1,
    )
    return fig
