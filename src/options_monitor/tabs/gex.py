"""GEX tab: options positioning and key levels."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from tractatus.calc.gex import (
    find_aggregate_wall_strikes,
    find_decision_zones,
    find_raw_wall_strikes,
    net_gex_by_price,
    net_gex_by_strike,
)
from tractatus.calc.gex_term_structure import compute_gex_term_structure
from tractatus.calc.vol import compute_risk_reversal

from options_monitor.charts.gex_aggregate import build_gex_aggregate_chart
from options_monitor.charts.gex_single import build_gex_single_expiry_chart
from options_monitor.charts.gex_term_structure import build_gex_term_structure_chart
from options_monitor.charts.skew_indicators import build_skew_indicators
from options_monitor.charts.vol_skew import build_vol_skew_chart
from options_monitor.data.intraday import (
    find_intraday_updated_at,
    find_latest_snapshots,
    list_expirations,
)
from options_monitor.data.options import (
    find_historical_snapshot_times,
    list_expirations_for_window_on_date,
    list_expirations_from_archive,
    list_snapshot_dates,
    list_snapshot_dates_for_expiry,
    load_historical_snapshot,
    load_latest_archived_single_expiry,
    load_latest_archived_window,
    load_options_snapshot,
    parquet_path_for_date,
)

_CHICAGO = ZoneInfo("America/Chicago")
_GEX_VIEWS = [
    "GEX",
    "Chains",
    "Gamma Heatmap",
]
_SINGLE_EXPIRY_VIEWS = {
    "Chains",
}


def _to_chicago_time(ts: pd.Timestamp | date | object) -> object:
    if isinstance(ts, pd.Timestamp):
        py_ts = ts.to_pydatetime()
        return py_ts.replace(tzinfo=UTC).astimezone(_CHICAGO).replace(tzinfo=None)
    if hasattr(ts, "replace"):
        return ts.replace(tzinfo=UTC).astimezone(_CHICAGO).replace(tzinfo=None)
    return ts


def _compute_spot_and_strike_range(options_df: pd.DataFrame, range_pct: float) -> tuple[float, int]:
    spot_series = pd.to_numeric(options_df["underlying_price"], errors="coerce").dropna()
    if spot_series.empty:
        raise ValueError("No valid underlying_price in options data.")
    spot = float(spot_series.iloc[0])
    strike_range = round(spot * range_pct / 100)
    return spot, strike_range


def _show_sample_caption(sampled_at: datetime, is_archive: bool = False) -> None:
    """Show a caption with the snapshot sample datetime in Chicago time."""
    if sampled_at.tzinfo is None:
        sampled_at = sampled_at.replace(tzinfo=UTC)
    ts_ct = sampled_at.astimezone(_CHICAGO).strftime("%Y-%m-%d %H:%M:%S CT")
    st.caption(ts_ct)


def _load_window_snapshot_data(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> tuple[pd.DataFrame, float, int, datetime | None, bool] | None:
    snapshots = find_latest_snapshots(
        symbol,
        start_date=start_date,
        days_out=days_out,
        include_0dte=include_0dte,
    )
    if snapshots:
        all_opts = pd.concat(
            [load_options_snapshot(path) for path in snapshots.values()],
            ignore_index=True,
        )
        spot, strike_range = _compute_spot_and_strike_range(all_opts, range_pct)
        updated_at = find_intraday_updated_at(symbol)
        return all_opts, spot, strike_range, updated_at, False

    # Fallback: load from most recent archived parquet
    archived = load_latest_archived_window(
        symbol, start_date=start_date, days_out=days_out, include_0dte=include_0dte
    )
    if archived is None:
        return None
    sampled_at, frames = archived
    all_opts = pd.concat(frames.values(), ignore_index=True)
    spot, strike_range = _compute_spot_and_strike_range(all_opts, range_pct)
    return all_opts, spot, strike_range, sampled_at, True


def _load_single_expiry_snapshot_data(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> tuple[pd.DataFrame, float, int, datetime | None, bool] | None:
    single_snapshots = find_latest_snapshots(
        symbol,
        start_date=selected_exp,
        days_out=0,
        include_0dte=True,
    )
    if single_snapshots:
        single_opts = load_options_snapshot(next(iter(single_snapshots.values())))
        updated_at = find_intraday_updated_at(symbol)
        spot, strike_range = _compute_spot_and_strike_range(single_opts, range_pct)
        return single_opts, spot, strike_range, updated_at, False
    # Fallback: load from most recent archived parquet
    result = load_latest_archived_single_expiry(symbol, selected_exp)
    if result is None:
        return None
    sampled_at, single_opts = result
    if single_opts.empty:
        return None
    spot, strike_range = _compute_spot_and_strike_range(single_opts, range_pct)
    return single_opts, spot, strike_range, sampled_at, True


def _select_single_expiry(symbol: str, today: date, options_dir: Path) -> str | None:
    available_exps_desc = sorted(
        list_expirations(symbol) or list_expirations_from_archive(symbol),
        reverse=True,
    )
    if not available_exps_desc:
        return None

    exp_options = [expiry.isoformat() for expiry in available_exps_desc]
    today_iso = today.isoformat()
    default_idx = next((i for i, exp in enumerate(exp_options) if exp == today_iso), 0)
    return str(
        st.selectbox(
            "Single expiry",
            options=exp_options,
            index=default_idx,
            key="gm_expiry",
        )
    )


def _render_gex_view(
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    days_out = int(
        st.radio(
            "Aggregate window",
            options=[5, 10, 20, 30],
            horizontal=True,
            key="gm_gex_days",
        )
    )
    loaded = _load_window_snapshot_data(
        symbol=symbol,
        start_date=today,
        days_out=days_out,
        include_0dte=include_0dte,
        range_pct=range_pct,
        options_dir=options_dir,
    )
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for next {days_out} days.")
        return

    all_opts, spot, strike_range, sampled_at, is_archive = loaded
    if sampled_at is not None:
        _show_sample_caption(sampled_at, is_archive)
    anchor_ts = pd.Timestamp(today)

    strike_gex = net_gex_by_strike(all_opts, spot=spot, strike_range=strike_range)

    raw_call_wall, raw_put_wall = find_raw_wall_strikes(
        all_opts, spot=spot, strike_range=strike_range
    )
    dw_call_wall, dw_put_wall = find_aggregate_wall_strikes(
        all_opts,
        spot=spot,
        strike_range=strike_range,
        method="distance_weighted_aggregate",
        anchor_date=anchor_ts,
    )
    cluster_call_wall, cluster_put_wall = find_aggregate_wall_strikes(
        all_opts,
        spot=spot,
        strike_range=strike_range,
        method="per_expiry_clustering",
        anchor_date=anchor_ts,
    )
    resistance_zones, support_zones = find_decision_zones(
        all_opts,
        spot=spot,
        strike_range=strike_range,
        anchor_date=anchor_ts,
        top_n=2,
    )

    with st.spinner("Computing GEX by price grid..."):
        price_gex = net_gex_by_price(all_opts, spot=spot, price_range=strike_range)

    fig_agg = build_gex_aggregate_chart(
        strike_gex,
        price_gex,
        spot,
        raw_call_wall=raw_call_wall,
        raw_put_wall=raw_put_wall,
        dw_call_wall=dw_call_wall,
        dw_put_wall=dw_put_wall,
        cluster_call_wall=cluster_call_wall,
        cluster_put_wall=cluster_put_wall,
        resistance_zones=resistance_zones,
        support_zones=support_zones,
        title=f"{symbol} GEX Aggregate ({days_out}d)",
    )
    st.plotly_chart(fig_agg, use_container_width=True)


def _render_gex_history_view(
    symbol: str,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    sample_dates = list_snapshot_dates(symbol)
    if not sample_dates:
        st.warning(f"No historical {symbol} options snapshots found.")
        return

    col_date, col_window = st.columns([2, 2])
    with col_date:
        selected_sample_date = st.date_input(
            "Sample date",
            value=sample_dates[-1],
            min_value=sample_dates[0],
            max_value=sample_dates[-1],
            key="gm_gex_history_sample_date",
        )
    with col_window:
        days_out = int(
            st.radio(
                "Aggregate window",
                options=[5, 10, 20, 30],
                horizontal=True,
                key="gm_gex_history_days",
            )
        )

    if selected_sample_date not in set(sample_dates):
        st.warning(f"No historical {symbol} snapshots found on {selected_sample_date.isoformat()}.")
        return

    expiries = list_expirations_for_window_on_date(
        symbol,
        sample_date=selected_sample_date,
        days_out=days_out,
        include_0dte=include_0dte,
    )
    if not expiries:
        st.warning(
            f"No {symbol} expirations found in the {days_out}d window on "
            f"{selected_sample_date.isoformat()}."
        )
        return

    parquet_path = parquet_path_for_date(symbol, selected_sample_date)
    if parquet_path is None:
        st.error(
            f"No parquet file for {symbol} on {selected_sample_date.isoformat()}. "
            "Compaction may not have run for this date."
        )
        return

    history_key = (
        symbol,
        selected_sample_date.isoformat(),
        days_out,
        include_0dte,
    )
    with st.spinner("Loading historical aggregate snapshots..."):
        if st.session_state.get("_gex_agg_history_key") != history_key:
            # Collect distinct snapshot times across all expiries in the window.
            all_times: set[datetime] = set()
            for expiry in expiries:
                all_times.update(find_historical_snapshot_times(expiry, parquet_path))
            replay_times = sorted(all_times)
            st.session_state["_gex_agg_history_key"] = history_key
            st.session_state["_gex_agg_history_replay_times"] = replay_times
        else:
            replay_times = st.session_state["_gex_agg_history_replay_times"]

    if not replay_times:
        st.warning(
            f"No historical {symbol} snapshots found for the selected aggregate window on "
            f"{selected_sample_date.isoformat()}."
        )
        return

    local_replay_times = [_to_chicago_time(ts) for ts in replay_times]
    slider_key = (
        symbol,
        selected_sample_date.isoformat(),
        days_out,
        include_0dte,
        len(local_replay_times),
    )
    if st.session_state.get("_gex_agg_history_slider_key") != slider_key:
        st.session_state["_gex_agg_history_slider_key"] = slider_key
        st.session_state["gm_gex_history_snapshot_time"] = local_replay_times[-1]

    if st.session_state.get("gm_gex_history_snapshot_time") not in local_replay_times:
        st.session_state["gm_gex_history_snapshot_time"] = local_replay_times[-1]

    st.select_slider(
        "Point in time (CT)",
        options=local_replay_times,
        key="gm_gex_history_snapshot_time",
        format_func=lambda ts: ts.strftime("%Y-%m-%d %H:%M:%S CT"),
    )
    selected_ts_local = st.session_state["gm_gex_history_snapshot_time"]
    replay_idx = local_replay_times.index(selected_ts_local)
    replay_time = replay_times[replay_idx]

    frames = [
        load_historical_snapshot(symbol, expiry, replay_time, parquet_path) for expiry in expiries
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        st.warning(
            f"No {symbol} expiry snapshots were available at "
            f"{selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')}."
        )
        return

    all_opts = pd.concat(frames, ignore_index=True)
    spot, strike_range = _compute_spot_and_strike_range(all_opts, range_pct)
    strike_gex = net_gex_by_strike(all_opts, spot=spot, strike_range=strike_range)
    snap_time = pd.Timestamp(replay_time)
    if snap_time.tzinfo is not None:
        snap_time = snap_time.tz_convert("UTC").tz_localize(None)
    with st.spinner("Computing historical GEX by price grid..."):
        price_gex = net_gex_by_price(
            all_opts,
            spot=spot,
            snap_time=snap_time,
            price_range=strike_range,
        )

    st.caption(
        f"Snapshot time: {selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')} | "
        f"Expiries: {len(frames)}"
    )
    fig_agg = build_gex_aggregate_chart(
        strike_gex,
        price_gex,
        spot,
        title=(
            f"{symbol} GEX History ({days_out}d) "
            f"({selected_sample_date.isoformat()} {selected_ts_local.strftime('%H:%M:%S')} CT)"
        ),
    )
    st.plotly_chart(fig_agg, use_container_width=True)


def _render_chains_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    loaded = _load_single_expiry_snapshot_data(symbol, selected_exp, range_pct, options_dir)
    if loaded is None:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    single_opts, spot, strike_range, sampled_at, is_archive = loaded
    if sampled_at is not None:
        _show_sample_caption(sampled_at, is_archive)
    rr_result = compute_risk_reversal(single_opts)
    if rr_result is not None:
        fig_rr = build_skew_indicators(rr_result, spot=spot)
        st.plotly_chart(fig_rr, use_container_width=True)

    fig_single = build_gex_single_expiry_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=f"{symbol} GEX {selected_exp}",
    )
    st.plotly_chart(fig_single, use_container_width=True)

    chain_view = st.segmented_control(
        "Chain chart",
        options=["Vol Skew", "Option Price", "Delta"],
        default="Vol Skew",
        selection_mode="single",
        key="gm_chain_view",
        label_visibility="collapsed",
    )

    if chain_view == "Vol Skew":
        fig_skew = build_vol_skew_chart(
            single_opts,
            spot=spot,
            strike_range=strike_range,
            title=f"{symbol} Vol Skew {selected_exp}",
        )
        st.plotly_chart(fig_skew, use_container_width=True)

    elif chain_view == "Option Price":
        price_series = st.radio(
            "Price series",
            options=["mark", "bid", "ask"],
            horizontal=True,
            key="gm_chain_price_series",
        )
        fig_price = build_vol_skew_chart(
            single_opts,
            spot=spot,
            strike_range=strike_range,
            title=f"{symbol} Option Price {selected_exp}",
            value_col=price_series,
            value_label="Price",
        )
        st.plotly_chart(fig_price, use_container_width=True)

    elif chain_view == "Delta":
        fig_delta = build_vol_skew_chart(
            single_opts,
            spot=spot,
            strike_range=strike_range,
            title=f"{symbol} Delta by Strike {selected_exp}",
            value_col="delta",
            value_label="Delta",
            allow_negative=True,
            abs_puts=True,
        )
        st.plotly_chart(fig_delta, use_container_width=True)


def _render_history_view(
    symbol: str,
    selected_exp: date,
    range_pct: float,
    options_dir: Path,
) -> None:
    sample_dates = list_snapshot_dates_for_expiry(symbol, selected_exp)
    if not sample_dates:
        st.warning(f"No {symbol} options snapshots found for {selected_exp.isoformat()}.")
        return

    selected_sample_date = st.date_input(
        "Sample date",
        value=sample_dates[-1],
        min_value=sample_dates[0],
        max_value=sample_dates[-1],
        key="gm_history_sample_date",
    )

    if selected_sample_date not in set(sample_dates):
        st.warning(
            f"No {symbol} snapshots found on {selected_sample_date.isoformat()} for "
            f"{selected_exp.isoformat()}."
        )
        return

    parquet_path = parquet_path_for_date(symbol, selected_sample_date)
    if parquet_path is None:
        st.error(
            f"No parquet file for {symbol} on {selected_sample_date.isoformat()}. "
            "Compaction may not have run for this date."
        )
        return

    history_key = (
        symbol,
        selected_exp.isoformat(),
        selected_sample_date.isoformat(),
        range_pct,
    )
    with st.spinner("Loading historical chain snapshots..."):
        if st.session_state.get("_gex_history_key") != history_key:
            snapshot_times = find_historical_snapshot_times(selected_exp, parquet_path)
            st.session_state["_gex_history_key"] = history_key
            st.session_state["_gex_history_snapshot_times"] = snapshot_times
        else:
            snapshot_times = st.session_state["_gex_history_snapshot_times"]

    if not snapshot_times:
        st.warning(
            f"No {symbol} snapshots found on {selected_sample_date.isoformat()} for "
            f"{selected_exp.isoformat()}."
        )
        return

    local_timestamps = [_to_chicago_time(ts) for ts in snapshot_times]
    if st.session_state.get("_gex_history_slider_key") != history_key:
        st.session_state["_gex_history_slider_key"] = history_key
        st.session_state["gm_history_snapshot_time"] = local_timestamps[-1]

    snapshot_idx = len(snapshot_times) - 1
    if len(snapshot_times) > 1:
        if st.session_state.get("gm_history_snapshot_time") not in local_timestamps:
            st.session_state["gm_history_snapshot_time"] = local_timestamps[-1]
        selected_ts_local = st.select_slider(
            "Point in time (CT)",
            options=local_timestamps,
            key="gm_history_snapshot_time",
            format_func=lambda ts: ts.strftime("%Y-%m-%d %H:%M:%S CT"),
        )
        snapshot_idx = local_timestamps.index(selected_ts_local)

    selected_ts = snapshot_times[snapshot_idx]
    ts_local_obj = local_timestamps[snapshot_idx]
    assert isinstance(ts_local_obj, datetime)
    selected_ts_local = ts_local_obj
    st.caption(f"Snapshot time: {selected_ts_local.strftime('%Y-%m-%d %H:%M:%S CT')}")

    single_opts = load_historical_snapshot(symbol, selected_exp, selected_ts, parquet_path)
    spot, strike_range = _compute_spot_and_strike_range(single_opts, range_pct)
    fig_single = build_gex_single_expiry_chart(
        single_opts,
        spot=spot,
        strike_range=strike_range,
        title=(
            f"{symbol} Chain GEX History {selected_exp} "
            f"({selected_sample_date.isoformat()} {selected_ts_local.strftime('%H:%M:%S')} CT)"
        ),
    )
    st.plotly_chart(fig_single, use_container_width=True)


def _render_gamma_heatmap_view(
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    options_dir: Path,
) -> None:
    gh_date_range = st.date_input(
        "Expiration date range",
        value=(today, today + timedelta(days=10)),
        key="gm_gh_dates",
    )
    gh_normalize = st.toggle(
        "Relative GEX (per-expiry normalized)",
        value=False,
        key="gm_gh_normalize",
    )

    if isinstance(gh_date_range, tuple) and len(gh_date_range) == 2:
        gh_start, gh_end = gh_date_range[0], gh_date_range[1]
    else:
        gh_start, gh_end = today, today + timedelta(days=10)

    loaded = _load_window_snapshot_data(
        symbol=symbol,
        start_date=gh_start,
        days_out=(gh_end - gh_start).days,
        include_0dte=include_0dte,
        range_pct=range_pct,
        options_dir=options_dir,
    )
    if loaded is None:
        st.warning(f"No {symbol} snapshots found for selected date range.")
        return

    all_opts, spot, strike_range, sampled_at, is_archive = loaded
    if sampled_at is not None:
        _show_sample_caption(sampled_at, is_archive)
    gh_key = (symbol, round(spot), strike_range, gh_start, gh_end, len(all_opts))
    with st.spinner("Computing GEX term structure..."):
        if st.session_state.get("_gh_key") != gh_key:
            if is_archive:
                exp_col = pd.to_datetime(all_opts["expiration_date"]).dt.date
                gh_frames = {exp: grp for exp, grp in all_opts.groupby(exp_col)}
            else:
                exp_col = pd.to_datetime(all_opts["expiration_date"]).dt.date
                gh_frames = {exp: grp for exp, grp in all_opts.groupby(exp_col)}
            gh_strikes, gh_expirations, gh_matrix = compute_gex_term_structure(
                gh_frames, spot=spot, strike_range=strike_range
            )
            st.session_state["_gh_key"] = gh_key
            st.session_state["_gh_strikes"] = gh_strikes
            st.session_state["_gh_expirations"] = gh_expirations
            st.session_state["_gh_matrix"] = gh_matrix
        else:
            gh_strikes = st.session_state["_gh_strikes"]
            gh_expirations = st.session_state["_gh_expirations"]
            gh_matrix = st.session_state["_gh_matrix"]

    gh_y_range: tuple[float, float] | None = None
    if gh_strikes and len(gh_strikes) >= 2:
        gh_strike_range = st.select_slider(
            "Strike range",
            options=gh_strikes,
            value=(gh_strikes[0], gh_strikes[-1]),
            key="gm_gh_strike_range",
        )
        gh_y_range = (float(gh_strike_range[0]), float(gh_strike_range[1]))

    fig_gh = build_gex_term_structure_chart(
        gh_strikes,
        gh_expirations,
        gh_matrix,
        spot=spot,
        normalize=gh_normalize,
        y_range=gh_y_range,
        title=f"{symbol} GEX Term Structure",
    )
    st.plotly_chart(fig_gh, use_container_width=True)


def _render_active_gex_view(
    active_view: str,
    symbol: str,
    today: date,
    include_0dte: bool,
    range_pct: float,
    selected_exp_str: str | None,
    options_dir: Path,
) -> None:
    if active_view == "GEX":
        _render_gex_view(symbol, today, include_0dte, range_pct, options_dir)
        return
    if active_view == "Gamma Heatmap":
        _render_gamma_heatmap_view(symbol, today, include_0dte, range_pct, options_dir)
        return
    if active_view not in _SINGLE_EXPIRY_VIEWS:
        raise ValueError(f"Unknown GEX view: {active_view}")

    if selected_exp_str is None:
        st.warning(f"No expirations available for {symbol}.")
        return

    selected_exp = date.fromisoformat(selected_exp_str)
    if active_view == "Chains":
        _render_chains_view(symbol, selected_exp, range_pct, options_dir)
        return
    raise ValueError(f"Unknown GEX view: {active_view}")


def render_gex_tab(options_dir: Path, candle_dir: Path) -> None:
    del candle_dir
    st.subheader("GEX")

    @st.fragment(run_every="5m")
    def _render() -> None:
        col_ctrl, col_chart = st.columns([1, 3])

        with col_ctrl:
            include_0dte = st.toggle("Include 0DTE", value=True, key="gm_0dte")
            symbol = str(st.session_state.get("global_symbol", "SPXW"))
            range_pct = float(
                st.slider(
                    "Strike range (% of spot)",
                    min_value=1,
                    max_value=25,
                    value=5,
                    step=1,
                    key="gm_range_pct",
                )
            )

        today = date.today()

        with col_chart:
            active_view = str(
                st.segmented_control(
                    "GEX View",
                    options=_GEX_VIEWS,
                    default="GEX",
                    selection_mode="single",
                    key="gm_view",
                    label_visibility="collapsed",
                )
            )

        selected_exp_str: str | None = None
        if active_view in _SINGLE_EXPIRY_VIEWS:
            with col_ctrl:
                st.divider()
                selected_exp_str = _select_single_expiry(symbol, today, options_dir)

        with col_chart:
            _render_active_gex_view(
                active_view=active_view,
                symbol=symbol,
                today=today,
                include_0dte=include_0dte,
                range_pct=range_pct,
                selected_exp_str=selected_exp_str,
                options_dir=options_dir,
            )

    _render()
