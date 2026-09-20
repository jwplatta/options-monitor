"""Smoke tests for chart builder functions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from options_monitor.charts.gex_aggregate import build_gex_aggregate_chart
from options_monitor.charts.gex_single import build_gex_single_expiry_chart
from options_monitor.charts.price import build_sma_price_chart
from options_monitor.charts.vix_term import build_vix_term_chart
from options_monitor.charts.vol_spread import build_iv_rv_chart
from options_monitor.charts.volume import build_sma_volume_chart
from options_monitor.data.candles import load_candles


@pytest.fixture()
def spx_day(candle_dir: Path) -> pd.DataFrame:
    return load_candles("SPX", "day", data_dir=candle_dir, start=date(2026, 1, 1))


def test_build_sma_price_chart_returns_figure(spx_day: pd.DataFrame) -> None:
    fig = build_sma_price_chart(spx_day, fast_window=5, slow_window=20)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # close + fast MA + slow MA


def test_build_sma_volume_chart_returns_figure(spx_day: pd.DataFrame) -> None:
    fig = build_sma_volume_chart(spx_day)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # volume bar + close + weekly VWAP


def test_build_iv_rv_chart_returns_figure() -> None:
    n = 30
    dates = pd.Series(pd.date_range("2026-01-01", periods=n))
    iv = pd.Series(np.full(n, 18.0))
    rv = pd.Series(np.full(n, 14.0))
    spread = pd.Series(np.full(n, 4.0))
    fig = build_iv_rv_chart(iv=iv, rv=rv, spread=spread, datetimes=dates)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3


def test_build_iv_rv_chart_raises_on_misaligned_series() -> None:
    with pytest.raises(ValueError, match="same length"):
        build_iv_rv_chart(
            iv=pd.Series([1.0, 2.0]),
            rv=pd.Series([1.0]),
            spread=pd.Series([1.0, 2.0]),
            datetimes=pd.Series(pd.date_range("2026-01-01", periods=2)),
        )


def test_build_vix_term_chart_without_vix1d(candle_dir: Path) -> None:
    vix = load_candles("VIX", "day", data_dir=candle_dir, start=date(2026, 1, 1))
    vix9d = load_candles("VIX9D", "day", data_dir=candle_dir, start=date(2026, 1, 1))
    fig = build_vix_term_chart(vix=vix, vix9d=vix9d)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # VIX + VIX9D only


def test_build_gex_aggregate_chart_returns_figure(spxw_opts: pd.DataFrame) -> None:
    from tractatus.calc.gex import net_gex_by_price, net_gex_by_strike

    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    strike_gex = net_gex_by_strike(spxw_opts, spot=spot)
    price_gex = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap, price_range=50.0)
    fig = build_gex_aggregate_chart(strike_gex=strike_gex, price_gex=price_gex, spot=spot)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # bars + line


def test_build_gex_aggregate_chart_adds_raw_walls() -> None:
    strike_gex = pd.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0],
            "net_gex": [-100.0, 50.0, 125.0],
        }
    )
    price_gex = pd.DataFrame(
        {
            "price": [95.0, 100.0, 105.0],
            "net_gex": [-50.0, 50.0, 100.0],
        }
    )

    fig = build_gex_aggregate_chart(
        strike_gex=strike_gex,
        price_gex=price_gex,
        spot=100.0,
        raw_call_wall=105.0,
        raw_put_wall=95.0,
    )

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    annotation_texts = {a.text for a in (fig.layout.annotations or [])}
    assert "CW 105" in annotation_texts
    assert "PW 95" in annotation_texts
    assert "Spot 100" in annotation_texts


def test_build_gex_aggregate_chart_adds_all_wall_types() -> None:
    strike_gex = pd.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0],
            "net_gex": [-100.0, 50.0, 125.0],
        }
    )
    price_gex = pd.DataFrame(
        {
            "price": [95.0, 100.0, 105.0],
            "net_gex": [-50.0, 50.0, 100.0],
        }
    )

    fig = build_gex_aggregate_chart(
        strike_gex=strike_gex,
        price_gex=price_gex,
        spot=100.0,
        raw_call_wall=105.0,
        raw_put_wall=95.0,
        dw_call_wall=104.0,
        dw_put_wall=96.0,
        cluster_call_wall=103.0,
        cluster_put_wall=97.0,
    )

    assert isinstance(fig, go.Figure)
    annotation_texts = {a.text for a in (fig.layout.annotations or [])}
    assert "CW 105" in annotation_texts
    assert "PW 95" in annotation_texts
    assert "CW-DW 104" in annotation_texts
    assert "PW-DW 96" in annotation_texts
    assert "CW-CL 103" in annotation_texts
    assert "PW-CL 97" in annotation_texts


def test_build_gex_aggregate_chart_adds_decision_zone_overlays() -> None:
    strike_gex = pd.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0],
            "net_gex": [-100.0, 50.0, 125.0],
        }
    )
    price_gex = pd.DataFrame(
        {
            "price": [95.0, 100.0, 105.0],
            "net_gex": [-50.0, 50.0, 100.0],
        }
    )

    fig = build_gex_aggregate_chart(
        strike_gex=strike_gex,
        price_gex=price_gex,
        spot=100.0,
        resistance_zones=[{"low": 100.0, "high": 110.0, "center": 105.0, "score": 1.0}],
        support_zones=[{"low": 90.0, "high": 100.0, "center": 95.0, "score": 1.0}],
    )

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    annotation_texts = {a.text for a in (fig.layout.annotations or [])}
    assert "R1 100–110" in annotation_texts
    assert "S1 90–100" in annotation_texts
    assert "Spot 100" in annotation_texts


def test_build_gex_single_expiry_chart_returns_figure(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    fig = build_gex_single_expiry_chart(spxw_opts, spot=spot)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # call bars + put bars
