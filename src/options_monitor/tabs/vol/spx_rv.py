"""SPX RV subtab: RV acceleration and vol-of-vol charts."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from options_monitor.charts.rv_acceleration import build_rv_acceleration_chart
from options_monitor.charts.vol_of_vol import build_vol_of_vol_chart
from options_monitor.data.candles import list_available_dates, load_candles


def render_spx_rv_tab() -> None:
    """Render the SPX RV subtab."""
    rv_c1, rv_c2, rv_c3, rv_c4, rv_c5 = st.columns([1, 1, 1, 1, 1])
    with rv_c1:
        freq_rv = (
            st.selectbox("Frequency", ["day", "1min", "5min", "30min"], index=0, key="rv_freq")
            or "day"
        )
    with rv_c2:
        rv_fast_days = int(
            st.number_input("RV Fast (days)", min_value=1, value=3, key="vol_rv_fast")
        )
    with rv_c3:
        rv_slow_days = int(
            st.number_input("RV Slow (days)", min_value=2, value=10, key="vol_rv_slow")
        )
    with rv_c4:
        vov_freq = (
            st.selectbox(
                "VoV Frequency", ["1min", "5min", "30min", "day"], index=0, key="vol_vov_freq"
            )
            or "1min"
        )
    with rv_c5:
        vov_n = int(st.number_input("VoV N (bars)", min_value=2, value=30, key="vol_vov_n"))
        vov_m = int(st.number_input("VoV M (bars)", min_value=2, value=60, key="vol_vov_m"))

    if rv_fast_days >= rv_slow_days:
        st.error(f"RV fast ({rv_fast_days}) must be less than slow ({rv_slow_days}).")
        return

    st.divider()

    try:
        start_avail_rv, end_avail_rv = list_available_dates("SPX", str(freq_rv))
    except FileNotFoundError:
        st.error("SPX data not available.")
        return

    today_rv = date.today()
    default_start_rv = max(date(today_rv.year, today_rv.month, 1), start_avail_rv.date())

    rv_date_c1, rv_date_c2, _ = st.columns([1, 1, 2])
    with rv_date_c1:
        start_rv = st.date_input("Start", value=default_start_rv, key="rv_start")
    with rv_date_c2:
        end_rv = st.date_input("End", value=end_avail_rv.date(), key="rv_end")

    lookback_rv = max(rv_slow_days, 30) * 3
    lookback_start_rv = date.fromisoformat(str(start_rv)) - timedelta(days=lookback_rv)
    spx_rv = load_candles("SPX", str(freq_rv), start=lookback_start_rv, end=end_rv)

    rv_fig = build_rv_acceleration_chart(
        spx_rv,
        fast_days=rv_fast_days,
        slow_days=rv_slow_days,
        freq=str(freq_rv),
        title=f"SPX RV Acceleration — {rv_fast_days}d vs {rv_slow_days}d",
    )
    start_trim_rv = pd.Timestamp(start_rv, tz="UTC")
    if str(freq_rv) in {"1min", "5min", "30min"}:
        mask = spx_rv["datetime"] >= start_trim_rv
        display_start = int(mask.idxmax()) if mask.any() else 0
        rv_fig.update_xaxes(range=[display_start - 0.5, len(spx_rv) - 0.5])
    else:
        rv_fig.update_xaxes(
            range=[start_trim_rv, pd.Timestamp(end_rv, tz="UTC") + pd.Timedelta(days=1)]
        )
    st.plotly_chart(rv_fig, use_container_width=True)

    _vov_bars_per_day = {"1min": 390, "5min": 78, "30min": 13, "day": 1}
    vov_bars_per_day = _vov_bars_per_day.get(str(vov_freq), 1)
    vov_lookback_days = ((vov_n + vov_m) // vov_bars_per_day + 1) * 2
    vov_lookback_start = date.fromisoformat(str(start_rv)) - timedelta(days=vov_lookback_days)
    try:
        spx_vov = load_candles("SPX", str(vov_freq), start=vov_lookback_start, end=end_rv)
        if spx_vov.empty:
            st.warning(f"No {vov_freq} SPX data for selected range.")
        else:
            vov_fig = build_vol_of_vol_chart(
                spx_vov,
                n_window=vov_n,
                m_window=vov_m,
                freq=str(vov_freq),
                display_start=date.fromisoformat(str(start_rv)),
                title=f"SPX Vol-of-Vol ({vov_freq}) — σ(N={vov_n}) · VoV(M={vov_m})",
            )
            st.plotly_chart(vov_fig, use_container_width=True)
    except FileNotFoundError:
        st.info(f"{vov_freq} SPX data not available for vol-of-vol chart.")
