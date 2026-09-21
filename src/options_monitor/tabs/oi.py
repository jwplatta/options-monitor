"""Open Interest subtab: OI matrix with z-score heatmap overlay."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from tractatus.calc.oi import build_oi_matrix
from tractatus.calc.oi_zscore import build_oi_bucket_stats, compute_oi_zscore_matrix

from options_monitor.config import OPTIONS_DIR, PARQUET_OPTIONS_DIR
from options_monitor.data.intraday import find_latest_snapshots
from options_monitor.data.options import load_historical_sample_window, load_options_snapshot

_CHICAGO = ZoneInfo("America/Chicago")


@st.cache_data(ttl=300, max_entries=5)
def _load_oi_historical_frames(
    symbol: str,
    lookback_days: int,
    interval_minutes: int,
    options_dir: Path,
) -> tuple[list[pd.DataFrame], list[datetime]]:
    """Load interval-downsampled historical chain snapshots for z-score bucket building.

    Queries DuckDB across all parquet files for the lookback window. Returns
    (frames, sample_datetimes) where each frame is one sampled_at slice and
    sample_datetimes are the corresponding UTC datetimes.
    """
    today = date.today()
    lookback_start = today - timedelta(days=lookback_days)
    parquet_glob = str(PARQUET_OPTIONS_DIR / "*" / "*" / "*" / f"{symbol}_samples_*.parquet")

    df = load_historical_sample_window(symbol, parquet_glob, lookback_start, interval_minutes)
    if df.empty:
        return [], []

    df["sampled_at"] = pd.to_datetime(df["sampled_at"], utc=True)

    frames: list[pd.DataFrame] = []
    sample_datetimes: list[datetime] = []
    for sampled_at, group in df.groupby("sampled_at", sort=True):
        frames.append(group.reset_index(drop=True))
        sample_datetimes.append(pd.Timestamp(str(sampled_at)).to_pydatetime())

    return frames, sample_datetimes


def render_oi_tab(options_dir: Path = OPTIONS_DIR) -> None:
    """Render the Open Interest z-score tab."""
    symbol = str(st.session_state.get("global_symbol", "SPXW"))
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
    with c1:
        oi_days_out = int(
            st.radio("Days Out", [7, 14, 21, 30], index=3, horizontal=True, key="oi_days_out")
        )
    with c2:
        oi_contract_type = str(
            st.radio("Contract", ["Call", "Put", "OTM"], index=0, horizontal=True, key="oi_ct")
        ).upper()
    with c3:
        oi_otm_pct = float(
            st.selectbox("Strike Range (±% OTM)", [2, 5, 10, 15], index=1, key="oi_otm_pct")
        )
    with c4:
        oi_lookback = int(
            st.selectbox("Lookback (days)", [10, 20, 30, 60, 90], index=2, key="oi_lookback")
        )
        oi_interval = int(st.selectbox("Interval (min)", [30, 60], index=1, key="oi_interval"))
    with c5:
        oi_include_0dte = st.toggle("Include 0DTE", value=True, key="oi_include_0dte")

    snapshot_paths = find_latest_snapshots(
        symbol,
        start_date=date.today(),
        days_out=oi_days_out,
        include_0dte=oi_include_0dte,
    )

    if not snapshot_paths:
        st.warning(f"No {symbol} snapshots found.")
        return

    loaded: dict[date, pd.DataFrame] = {}
    spot: float = 0.0
    for expiry, path in snapshot_paths.items():
        try:
            snap = load_options_snapshot(path)
            loaded[expiry] = snap
            if spot == 0.0 and not snap["underlying_price"].empty:
                spot = float(snap["underlying_price"].iloc[0])
        except FileNotFoundError:
            continue

    with c6:
        if spot:
            st.metric("Spot (SPXW)", f"{spot:,.2f}")

    oi_matrix = build_oi_matrix(loaded, contract_type=oi_contract_type, spot=spot)

    if oi_matrix.empty:
        st.warning("No open interest data available for the selected parameters.")
        return

    zscore_matrix: pd.DataFrame | None = None
    with st.spinner("Loading historical data for z-scores…"):
        hist_frames, hist_datetimes = _load_oi_historical_frames(
            symbol, oi_lookback, oi_interval, options_dir
        )
    if hist_frames:
        bucket_stats = build_oi_bucket_stats(hist_frames, hist_datetimes)
        zscore_matrix = compute_oi_zscore_matrix(
            loaded,
            bucket_stats,
            spot=spot,
            contract_type=oi_contract_type,
            now=datetime.now(_CHICAGO),
        )
    _render_oi_table(
        oi_matrix,
        spot=spot,
        otm_pct=oi_otm_pct,
        zscore_matrix=zscore_matrix,
        zscore_sample_days=len(set(dt.date() for dt in hist_datetimes)),
    )


def _render_oi_table(
    oi_matrix: pd.DataFrame,
    spot: float,
    otm_pct: float,
    zscore_matrix: pd.DataFrame | None = None,
    zscore_sample_days: int = 0,
) -> None:
    """Render the OI matrix as a scrollable styled dataframe."""
    strikes = np.array(oi_matrix.columns.tolist(), dtype=float)

    lo = spot * (1 - otm_pct / 100)
    hi = spot * (1 + otm_pct / 100)
    mask = (strikes >= lo) & (strikes <= hi)
    oi_filtered = oi_matrix.loc[:, mask]

    if oi_filtered.empty:
        st.warning("No strikes in the selected OTM range.")
        return

    z_aligned: pd.DataFrame | None = None
    if zscore_matrix is not None and not zscore_matrix.empty:
        shared_rows = oi_filtered.index.intersection(zscore_matrix.index)
        shared_cols = oi_filtered.columns.intersection(zscore_matrix.columns)
        if len(shared_rows) and len(shared_cols):
            z_aligned = zscore_matrix.loc[shared_rows, shared_cols].reindex(
                index=oi_filtered.index, columns=oi_filtered.columns
            )

    filtered_strikes = np.array(oi_filtered.columns.tolist(), dtype=float)
    nearest_strike = filtered_strikes[int(np.argmin(np.abs(filtered_strikes - spot)))]

    formatted = oi_filtered.copy()
    for col in formatted.columns:
        formatted[col] = formatted[col].apply(
            lambda v: f"{int(v):,}" if pd.notna(v) and v > 0 else ""
        )

    str_index = [str(d) for d in oi_filtered.index]
    str_cols = [f"{int(c)}" for c in oi_filtered.columns]
    formatted.index = str_index
    formatted.index.name = "Expiry \\ Strike"
    formatted.columns = str_cols

    nearest_col_name = f"{int(nearest_strike)}"

    if z_aligned is not None:
        z_display = z_aligned.copy()
        z_display.index = str_index[: len(z_display)]
        z_display.columns = [f"{int(c)}" for c in z_aligned.columns]
    else:
        z_display = None

    if z_display is not None:
        _render_zscore_legend()

    # TODO: extract to shared zscore style helper
    def _zscore_color(z: float) -> tuple[str, str]:
        z_clamped = max(-3.0, min(3.0, z))
        t = abs(z_clamped) / 3.0
        if z_clamped >= 0:
            r = int(30 * (1 - t) + 5 * t)
            g = int(30 * (1 - t) + 83 * t)
            b = int(30 * (1 - t) + 45 * t)
            fg = "#4ade80" if t > 0.4 else "#e0e0e0"
        else:
            r = int(30 * (1 - t) + 127 * t)
            g = int(30 * (1 - t) + 10 * t)
            b = int(30 * (1 - t) + 10 * t)
            fg = "#f87171" if t > 0.4 else "#e0e0e0"
        return f"#{r:02x}{g:02x}{b:02x}", fg

    def _cell_style(col: pd.Series) -> list[str]:
        col_name = str(col.name)
        styles: list[str] = []
        for row_label in col.index:
            z = (
                float(z_display.loc[row_label, col_name])
                if z_display is not None
                and col_name in z_display.columns
                and row_label in z_display.index
                and pd.notna(z_display.loc[row_label, col_name])
                else None
            )
            if z is not None:
                bg, fg = _zscore_color(z)
                styles.append(f"background-color: {bg}; color: {fg}")
            elif col_name == nearest_col_name:
                styles.append("background-color: #1a3a6a; color: #7dd3fc")
            else:
                styles.append("")
        return styles

    styled = formatted.style.apply(_cell_style, axis=0)
    n_rows = len(oi_filtered)
    table_height = 38 + n_rows * 28
    st.dataframe(styled, use_container_width=True, height=table_height)
    if zscore_sample_days:
        st.caption(f"z-scores computed from n={zscore_sample_days} sample days")


def _render_zscore_legend() -> None:
    """Render a compact red→neutral→green gradient legend for z-score coloring."""
    # TODO: extract to shared zscore style helper
    stops = [
        (-3, "#7f0a0a", "#f87171"),
        (-2, "#550a0a", "#f87171"),
        (-1, "#2a1010", "#e0e0e0"),
        (0, "#1e1e1e", "#e0e0e0"),
        (1, "#0a2a10", "#e0e0e0"),
        (2, "#055320", "#4ade80"),
        (3, "#05532d", "#4ade80"),
    ]
    cells = "".join(
        f'<td style="background:{bg};color:{fg};padding:2px 8px;font-size:11px;'
        f'text-align:center;border:1px solid #333">z={z}</td>'
        for z, bg, fg in stops
    )
    st.markdown(
        f'<table style="border-collapse:collapse;margin-bottom:6px"><tr>{cells}</tr></table>',
        unsafe_allow_html=True,
    )
