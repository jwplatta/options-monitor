"""Flow tab: Flow Tape and Flow Profile charts for SPXW option activity."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from options_monitor.calc.flow import compute_intraday_flow
from options_monitor.calc.flow_profile import compute_flow_profile
from options_monitor.calc.flow_tape import compute_flow_tape
from options_monitor.charts.flow_heatmap import build_flow_heatmap_chart
from options_monitor.charts.flow_profile import build_flow_profile_chart
from options_monitor.charts.flow_tape import build_flow_tape_chart
from options_monitor.data.intraday import find_latest_snapshots, list_expirations
from options_monitor.data.options import (
    find_all_snapshots_for_expiry,
    find_snapshots_for_expiry_on_date,
    list_snapshot_dates,
    load_historical_expiry,
    load_options_snapshot,
    parquet_path_for_date,
)

_CONTRACT_MAP = {"Both": "BOTH", "Calls": "CALL", "Puts": "PUT"}
_CHICAGO = ZoneInfo("America/Chicago")


def _to_chicago(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(_CHICAGO).replace(tzinfo=None)


def _get_spot(snapshots: list[tuple[datetime, Path]]) -> float | None:
    if not snapshots:
        return None
    latest_df = load_options_snapshot(snapshots[-1][1])
    spot_series = pd.to_numeric(latest_df["underlying_price"], errors="coerce").dropna()
    return float(spot_series.iloc[0]) if not spot_series.empty else None


def _load_parquet_preloaded(symbol: str, expiry: date, sample_date: date) -> pd.DataFrame:
    """Load historical expiry data from parquet and set _ts as UTC datetime.

    Raises FileNotFoundError if no parquet file exists for the given date.
    """
    parquet_path = parquet_path_for_date(symbol, sample_date)
    if parquet_path is None:
        raise FileNotFoundError(
            f"No parquet file for {symbol} on {sample_date}. "
            "Compaction may not have run for this date."
        )
    df = load_historical_expiry(symbol, expiry, sample_date, parquet_path)
    df["_ts"] = pd.to_datetime(df["sampled_at"], utc=True)
    return df


def _load_tape(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    sample_date: date,
    lookback_window: int,
    mode: str,
    contract_filter: str,
    selected_exp: date,
    ema_span: int,
    symbol: str = "SPXW",
    preloaded: pd.DataFrame | None = None,
) -> tuple[list[datetime], list[float], list[float], list[float], list[float]]:
    """Compute (or retrieve from cache) flow tape data for the given parameters."""
    tape_key = (
        symbol,
        selected_exp.isoformat(),
        sample_date.isoformat(),
        lookback_window,
        mode,
        contract_filter,
        ema_span,
        str(snapshots[-1][1])
        if (preloaded is None and snapshots)
        else len(preloaded)
        if preloaded is not None
        else 0,
    )
    if st.session_state.get("_fl_tape_key") != tape_key:
        with st.spinner("Computing flow tape..."):
            timestamps, call_flow, put_flow, raw_call, raw_put = compute_flow_tape(
                snapshots,
                spot=spot,
                sample_date=sample_date,
                lookback_window=lookback_window,
                mode=mode,
                contract_filter=contract_filter,
                ema_span=ema_span,
                preloaded=preloaded,
            )
        st.session_state["_fl_tape_key"] = tape_key
        st.session_state["_fl_tape_timestamps"] = timestamps
        st.session_state["_fl_tape_call"] = call_flow
        st.session_state["_fl_tape_put"] = put_flow
        st.session_state["_fl_tape_raw_call"] = raw_call
        st.session_state["_fl_tape_raw_put"] = raw_put
    else:
        timestamps = st.session_state["_fl_tape_timestamps"]
        call_flow = st.session_state["_fl_tape_call"]
        put_flow = st.session_state["_fl_tape_put"]
        raw_call = st.session_state["_fl_tape_raw_call"]
        raw_put = st.session_state["_fl_tape_raw_put"]
    return timestamps, call_flow, put_flow, raw_call, raw_put


def _render_flow_tape_view(
    snapshots: list[tuple[datetime, Path]],
    spot: float,
    sample_date: date,
    lookback_window: int,
    contract_filter: str,
    selected_exp: date,
    ema_span: int,
    symbol: str = "SPXW",
    preloaded: pd.DataFrame | None = None,
) -> None:
    timestamps, new_call, new_put, raw_call, raw_put = _load_tape(
        snapshots,
        spot,
        sample_date,
        lookback_window,
        "lookback",
        contract_filter,
        selected_exp,
        ema_span,
        symbol=symbol,
        preloaded=preloaded,
    )
    _, cum_call, cum_put, _, _ = _load_tape(
        snapshots,
        spot,
        sample_date,
        lookback_window,
        "cumulative",
        contract_filter,
        selected_exp,
        ema_span,
        symbol=symbol,
        preloaded=preloaded,
    )
    if not timestamps:
        st.warning("No flow data for selected date/expiry.")
        return
    fig = build_flow_tape_chart(
        timestamps,
        new_call,
        new_put,
        cum_call,
        cum_put,
        raw_call,
        raw_put,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_flow_profile_view(
    snapshots: list[tuple[datetime, Path]],
    sample_date: date,
    lookback_window: int,
    contract_filter: str,
    selected_exp: date,
    spot: float,
    range_pct: float,
    symbol: str = "SPXW",
    preloaded: pd.DataFrame | None = None,
) -> None:
    # Build ordered list of session snapshot timestamps for the rewind slider.
    if preloaded is not None:
        session_ts = sorted(preloaded["_ts"].dropna().unique().tolist())
    else:
        session_snapshots = sorted(
            [(ts, path) for ts, path in snapshots if _to_chicago(ts).date() == sample_date],
            key=lambda x: x[0],
        )
        if not session_snapshots:
            st.warning("No flow data for selected date/expiry.")
            return
        session_ts = [ts for ts, _ in session_snapshots]

    if not session_ts:
        st.warning("No flow data for selected date/expiry.")
        return
    session_ts_ct = [_to_chicago(ts) for ts in session_ts]
    ts_labels = [t.strftime("%H:%M") for t in session_ts_ct]

    # Default to latest snapshot; slider lets user rewind.
    selected_idx = st.select_slider(
        "As of",
        options=list(range(len(ts_labels))),
        value=len(ts_labels) - 1,
        format_func=lambda i: ts_labels[i],
        key="fl_profile_as_of",
    )
    as_of_ts = session_ts[selected_idx]

    profile_key = (
        symbol,
        selected_exp.isoformat(),
        sample_date.isoformat(),
        lookback_window,
        contract_filter,
        as_of_ts.isoformat(),
        range_pct,
    )
    if st.session_state.get("_fl_profile_key") != profile_key:
        with st.spinner("Computing flow profile..."):
            strikes, call_flow, put_flow = compute_flow_profile(
                snapshots,
                sample_date=sample_date,
                lookback_window=lookback_window,
                contract_filter=contract_filter,
                as_of=as_of_ts,
                preloaded=preloaded,
            )
        st.session_state["_fl_profile_key"] = profile_key
        st.session_state["_fl_profile_strikes"] = strikes
        st.session_state["_fl_profile_call"] = call_flow
        st.session_state["_fl_profile_put"] = put_flow
    else:
        strikes = st.session_state["_fl_profile_strikes"]
        call_flow = st.session_state["_fl_profile_call"]
        put_flow = st.session_state["_fl_profile_put"]

    if not strikes:
        st.warning("No flow data for selected date/expiry.")
        return

    # Filter to strikes within range_pct of spot before charting.
    half_range = spot * range_pct / 100
    filtered = [
        (s, c, p)
        for s, c, p in zip(strikes, call_flow, put_flow, strict=True)
        if abs(s - spot) <= half_range
    ]
    if filtered:
        f_strikes, f_call, f_put = zip(*filtered, strict=False)
        strikes_plot = list(f_strikes)
        call_plot = list(f_call)
        put_plot = list(f_put)
    else:
        strikes_plot, call_plot, put_plot = strikes, call_flow, put_flow

    as_of_label = session_ts_ct[selected_idx].strftime("%H:%M")
    fig = build_flow_profile_chart(
        strikes_plot,
        call_plot,
        put_plot,
        title=(
            f"Flow Profile — {symbol} {selected_exp.isoformat()} "
            f"({sample_date.isoformat()} as of {as_of_label})"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_intraday_flow_view(
    symbol: str,
    selected_exp: date,
    sample_date: date,
    spot: float,
    range_pct: float,
    options_dir: Path,
    preloaded: pd.DataFrame | None = None,
) -> None:
    if preloaded is not None:
        all_expiry_snapshots: list[tuple[datetime, Path]] = []
    else:
        all_expiry_snapshots = find_all_snapshots_for_expiry(
            symbol,
            expiry=selected_exp,
        )

    col_ct, col_wt = st.columns([3, 1])
    with col_ct:
        ct_filter = str(
            st.radio(
                "Contract type",
                options=["ALL", "CALL", "PUT"],
                horizontal=True,
                key="fl_intraday_ct",
            )
        )
    with col_wt:
        weight_by_delta = st.toggle("Weight by delta", value=True, key="fl_intraday_weight_delta")
    bucket_minutes = int(
        st.select_slider(
            "Sample interval (minutes)",
            options=[1, 5, 10, 15, 20, 25, 30],
            value=5,
            key="fl_intraday_bucket",
        )
    )

    flow_key = (
        symbol,
        selected_exp.isoformat(),
        round(spot),
        round(spot * range_pct / 100),
        ct_filter,
        bucket_minutes,
        weight_by_delta,
        sample_date,
        len(all_expiry_snapshots) if preloaded is None else len(preloaded),
    )
    with st.spinner("Computing intraday flow..."):
        if st.session_state.get("_fl_intraday_key") != flow_key:
            flow_strikes, flow_timestamps, flow_matrix, flow_prices = compute_intraday_flow(
                all_expiry_snapshots,
                spot=spot,
                moneyness_pct=range_pct / 100,
                contract_filter=ct_filter,
                bucket_minutes=bucket_minutes,
                weight_by_delta=weight_by_delta,
                target_date=sample_date,
                preloaded=preloaded,
            )
            st.session_state["_fl_intraday_key"] = flow_key
            st.session_state["_fl_intraday_strikes"] = flow_strikes
            st.session_state["_fl_intraday_timestamps"] = flow_timestamps
            st.session_state["_fl_intraday_matrix"] = flow_matrix
            st.session_state["_fl_intraday_prices"] = flow_prices
        else:
            flow_strikes = st.session_state["_fl_intraday_strikes"]
            flow_timestamps = st.session_state["_fl_intraday_timestamps"]
            flow_matrix = st.session_state["_fl_intraday_matrix"]
            flow_prices = st.session_state["_fl_intraday_prices"]

        fig_flow = build_flow_heatmap_chart(
            flow_strikes,
            flow_timestamps,
            flow_matrix,
            prices=flow_prices,
            title=f"{symbol} Intraday Flow {selected_exp}",
        )
    st.plotly_chart(fig_flow, use_container_width=True)


def render_flow_tab(options_dir: Path) -> None:
    """Render the Flow tab with Flow Tape and Flow Profile charts."""
    symbol = str(st.session_state.get("global_symbol", "SPXW"))
    st.subheader("Flow")

    col_ctrl, col_chart = st.columns([1, 3])

    with col_ctrl:
        # Sample date selection.
        today = date.today()
        sample_dates = list_snapshot_dates(symbol)
        if sample_dates:
            sample_date = st.date_input(
                "Sample date",
                value=sample_dates[-1],
                min_value=sample_dates[0],
                max_value=today,
                key="fl_sample_date",
            )
        else:
            # No local archive — default to today (intraday path).
            sample_date = today

        # Expiration selection — use intraday index for today, archive for past dates.
        all_expiries = list_expirations(symbol)
        available_expiries = [e for e in all_expiries if e >= sample_date]
        if not available_expiries:
            st.error("No expirations available for selected date.")
            return

        default_exp_idx = next((i for i, e in enumerate(available_expiries) if e == sample_date), 0)
        selected_exp_str = st.selectbox(
            "Expiration",
            options=[e.isoformat() for e in available_expiries],
            index=default_exp_idx,
            key="fl_expiry",
        )
        selected_exp = date.fromisoformat(str(selected_exp_str))

        st.divider()

        lookback_window = int(
            st.select_slider(
                "Lookback window (min)",
                options=[1, 5, 10, 15, 20],
                value=5,
                key="fl_lookback",
            )
        )
        ema_span = int(
            st.select_slider(
                "EMA span (min)",
                options=[1, 5, 10, 15, 20],
                value=5,
                key="fl_ema_span",
            )
        )
        contract_label = str(
            st.radio(
                "Contracts",
                options=["Both", "Calls", "Puts"],
                horizontal=True,
                key="fl_contracts",
            )
        )
        range_pct = float(
            st.slider(
                "Strike range (% of spot)",
                min_value=1,
                max_value=25,
                value=3,
                step=1,
                key="fl_range_pct",
            )
        )

    contract_filter = _CONTRACT_MAP[contract_label]

    # Route: historical dates use parquet; today uses intraday MinIO then local CSV fallback.
    preloaded: pd.DataFrame | None = None
    snapshots: list[tuple[datetime, Path]] = []
    spot: float = 0.0

    if sample_date < today:
        try:
            preloaded = _load_parquet_preloaded(symbol, selected_exp, sample_date)
        except FileNotFoundError as e:
            with col_chart:
                st.error(str(e))
            return
        spot_series = pd.to_numeric(preloaded["underlying_price"], errors="coerce").dropna()
        if spot_series.empty:
            with col_chart:
                st.warning("Could not determine spot price from parquet data.")
            return
        spot = float(spot_series.iloc[-1])
    else:
        # Try intraday MinIO first.
        intraday = find_latest_snapshots(
            symbol,
            start_date=selected_exp,
            days_out=0,
            include_0dte=True,
        )
        if intraday:
            uri = intraday.get(selected_exp)
            if uri:
                preloaded = load_options_snapshot(uri)
                preloaded["_ts"] = pd.to_datetime(
                    preloaded.get("sampled_at", pd.Series(dtype="object")), utc=True
                )
                spot_series = pd.to_numeric(preloaded["underlying_price"], errors="coerce").dropna()
                spot = float(spot_series.iloc[-1]) if not spot_series.empty else 0.0

        # Fall back to local CSV snapshots.
        if preloaded is None:
            snapshots = find_snapshots_for_expiry_on_date(
                symbol,
                expiry=selected_exp,
                sample_date=sample_date,
            )
            if snapshots:
                spot = _get_spot(snapshots) or 0.0

        if preloaded is None and not snapshots:
            with col_chart:
                st.warning(
                    f"No snapshots found for {symbol} expiry {selected_exp} on {sample_date}."
                )
            return
        if spot == 0.0:
            with col_chart:
                st.warning("Could not determine spot price from snapshots.")
            return

    with col_chart:
        active_view = str(
            st.segmented_control(
                "Flow View",
                options=["Flow Tape", "Flow Profile", "Intraday Flow"],
                default="Flow Tape",
                selection_mode="single",
                key="fl_view",
                label_visibility="collapsed",
            )
        )

        if active_view == "Flow Tape":
            _render_flow_tape_view(
                snapshots,
                spot=spot,
                sample_date=sample_date,
                lookback_window=lookback_window,
                contract_filter=contract_filter,
                selected_exp=selected_exp,
                ema_span=ema_span,
                symbol=symbol,
                preloaded=preloaded,
            )
        elif active_view == "Flow Profile":
            _render_flow_profile_view(
                snapshots,
                sample_date=sample_date,
                lookback_window=lookback_window,
                contract_filter=contract_filter,
                selected_exp=selected_exp,
                spot=spot,
                range_pct=range_pct,
                symbol=symbol,
                preloaded=preloaded,
            )
        else:
            _render_intraday_flow_view(
                symbol=symbol,
                selected_exp=selected_exp,
                sample_date=sample_date,
                spot=spot,
                range_pct=range_pct,
                options_dir=options_dir,
                preloaded=preloaded,
            )
