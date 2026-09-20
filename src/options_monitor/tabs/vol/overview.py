"""Overview subtab: IV vs realized vol, VIX term structure."""

from __future__ import annotations

import contextlib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from tractatus.calc.vol import iv_rv_spread, realized_vol, vix_spx_correlation

from options_monitor.charts.vix_term import build_vix_term_chart
from options_monitor.charts.vol_spread import build_iv_rv_chart
from options_monitor.data.candles import list_available_dates, load_candles


def render_overview_tab(candle_dir: Path) -> None:
    """Render the Overview subtab."""
    ov_c1, ov_c2, ov_c3, ov_c4 = st.columns([1, 1, 1, 1])
    with ov_c1:
        window_choice = st.radio("Window", ["9D", "30D"], horizontal=True, key="vol_window")
    with ov_c2:
        freq_ov = (
            st.selectbox("Frequency", ["day", "1min", "5min", "30min"], index=0, key="vol_freq")
            or "day"
        )

    try:
        start_avail, end_avail = list_available_dates("SPX", str(freq_ov), data_dir=candle_dir)
    except FileNotFoundError:
        st.error("SPX data not available.")
        return

    today = date.today()
    default_start = max(date(today.year, today.month, 1), start_avail.date())

    with ov_c3:
        start_sel = st.date_input("Start", value=default_start, key="vol_start")
    with ov_c4:
        end_sel = st.date_input("End", value=end_avail.date(), key="vol_end")

    st.divider()

    window_days = 9 if window_choice == "9D" else 30
    iv_symbol = "VIX9D" if window_choice == "9D" else "VIX"

    _bars_per_day = {"day": 1, "30min": 13, "5min": 78, "1min": 390}
    f_per_day = _bars_per_day.get(str(freq_ov), 1)
    window_bars = window_days * f_per_day
    ann_factor = 252 * f_per_day

    lookback_start = date.fromisoformat(str(start_sel)) - timedelta(days=window_days * 3)
    spx_ov = load_candles(
        "SPX", str(freq_ov), start=lookback_start, end=end_sel, data_dir=candle_dir
    )

    try:
        iv_candles = load_candles(
            iv_symbol, str(freq_ov), start=lookback_start, end=end_sel, data_dir=candle_dir
        )
    except FileNotFoundError:
        st.error(f"{iv_symbol} data not available for frequency {freq_ov}.")
        return

    rv_ov = realized_vol(spx_ov["close"], window=window_bars, periods_per_year=ann_factor)
    merged = pd.merge(
        spx_ov[["datetime"]].assign(rv=rv_ov.values),
        iv_candles[["datetime", "close"]].rename(columns={"close": "iv"}),
        on="datetime",
        how="inner",
    ).dropna()

    start_trim = pd.Timestamp(start_sel, tz="UTC")
    merged = merged[merged["datetime"] >= start_trim].reset_index(drop=True)

    if merged.empty:
        st.warning("No overlapping data for selected range.")
        return

    spread = iv_rv_spread(merged["iv"], merged["rv"])

    try:
        vix_full = load_candles(
            "VIX", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
        )
        corr = vix_spx_correlation(spx_ov, vix_full)
        st.metric(f"VIX-SPX Correlation ({freq_ov})", f"{corr:.3f}")
    except FileNotFoundError:
        st.info(f"VIX data not available for frequency {freq_ov}.")

    fig = build_iv_rv_chart(
        iv=merged["iv"],
        rv=merged["rv"],
        spread=spread,
        datetimes=merged["datetime"],
        window_label=str(window_choice),
        freq=str(freq_ov),
    )
    st.plotly_chart(fig, use_container_width=True)

    try:
        vix = load_candles("VIX", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir)
        vix9d = load_candles(
            "VIX9D", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
        )
        vix1d: pd.DataFrame | None = None
        if str(freq_ov) != "day":
            with contextlib.suppress(FileNotFoundError):
                vix1d = load_candles(
                    "VIX1D", str(freq_ov), start=start_sel, end=end_sel, data_dir=candle_dir
                )
        st.plotly_chart(
            build_vix_term_chart(vix, vix9d, vix1d, freq=str(freq_ov)),
            use_container_width=True,
        )
    except FileNotFoundError as e:
        st.info(f"VIX term structure incomplete: {e}")
