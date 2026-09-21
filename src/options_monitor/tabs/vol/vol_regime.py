"""Vol Regime subtab: IV z-score vs Risk Reversal z-score scatter."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from tractatus.calc.vol import compute_risk_reversal
from tractatus.tickrake.client import TickrakeClient
from tractatus.tickrake.config import TickrakeConfig

from options_monitor.calc.vol_regime import build_vol_regime_row, compute_atm_iv
from options_monitor.charts.vol_regime import build_vol_regime_chart
from options_monitor.config import OPTIONS_DIR, PARQUET_OPTIONS_DIR
from options_monitor.data.options import (
    _DUCKDB_CONN,
    _OPTIONS_DTYPES,
    find_latest_snapshots,
    list_snapshot_dates,
    load_options_snapshot,
)

_TARGET_DTE_OPTIONS = [5, 15, 30, 45]
_LOOKBACK_OPTIONS = [30, 45, 60]


def _default_client() -> TickrakeClient:
    return TickrakeClient(TickrakeConfig.from_env())


def _pick_expiry(expirations: list[date], today: date, target_dte: int) -> date | None:
    """Pick the expiration closest to *target_dte* days from *today*."""
    target_date = today + timedelta(days=target_dte)
    valid = [e for e in expirations if e >= today]
    if not valid:
        return None
    return min(valid, key=lambda e: abs((e - target_date).days))


def _filter_snapshot_to_expiry(df: pd.DataFrame, expiry: date) -> pd.DataFrame:
    """Keep only rows matching *expiry*."""
    exp_str = expiry.isoformat()
    return df[df["expiration_date"].astype(str).str.startswith(exp_str)]


@st.cache_data(ttl=300, max_entries=20)
def _load_eod_snapshot_for_expiry(
    symbol: str,
    sample_date: date,
    expiry: date,
    _parquet_dir: str,
) -> pd.DataFrame:
    """Load the last intraday snapshot for a symbol/date/expiry from archived parquet."""
    parquet_path = (
        Path(_parquet_dir)
        / f"{sample_date.year:04d}"
        / f"{sample_date.month:02d}"
        / f"{sample_date.day:02d}"
        / f"{symbol}_samples_{sample_date.isoformat()}.parquet"
    )
    if not parquet_path.exists():
        # Try downloading via archive client
        client = _default_client()
        result = client.options_archive.get_parquet_path(symbol, sample_date)
        if result is None:
            return pd.DataFrame()
        parquet_path = result

    expiry_str = expiry.isoformat()
    try:
        df = _DUCKDB_CONN.execute(
            """
            WITH last_sample AS (
                SELECT MAX(sampled_at) AS max_sa
                FROM read_parquet(?)
                WHERE expiration_date = ?
            )
            SELECT t.*
            FROM read_parquet(?) t, last_sample ls
            WHERE t.expiration_date = ?
              AND t.sampled_at = ls.max_sa
            """,
            [str(parquet_path), expiry_str, str(parquet_path), expiry_str],
        ).df()
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=10)
def _compute_vol_regime_data(
    symbols: tuple[str, ...],
    target_dte: int,
    lookback_days: int,
    _parquet_dir: str,
) -> pd.DataFrame:
    """Compute vol regime z-scores for all symbols."""
    today = date.today()
    client = _default_client()
    rows: list[dict[str, object]] = []

    for symbol in symbols:
        # Get current snapshot expirations
        try:
            current_snaps = find_latest_snapshots(symbol, today, target_dte + 15)
        except Exception:
            continue

        if not current_snaps:
            continue

        # Pick expiry closest to target DTE
        expiry = _pick_expiry(list(current_snaps.keys()), today, target_dte)
        if expiry is None:
            continue

        # Load current snapshot
        snap_uri = current_snaps.get(expiry)
        if snap_uri is None:
            # Try nearest available expiry
            by_dte = sorted(
                current_snaps.keys(),
                key=lambda e: abs((e - today).days - target_dte),
            )
            for exp in by_dte:
                if exp in current_snaps:
                    expiry = exp
                    snap_uri = current_snaps[exp]
                    break
        if snap_uri is None:
            continue

        try:
            current_df = load_options_snapshot(snap_uri)
        except Exception:
            continue

        current_expiry_df = _filter_snapshot_to_expiry(current_df, expiry)
        if current_expiry_df.empty:
            continue

        spot_series = current_expiry_df["underlying_price"].dropna()
        spot = float(spot_series.iloc[0]) if not spot_series.empty else 0.0
        if spot <= 0:
            continue

        current_iv = compute_atm_iv(current_expiry_df, spot)
        rr_result = compute_risk_reversal(current_expiry_df)
        if current_iv is None or rr_result is None:
            continue
        current_rr = rr_result.rr

        # Load historical data
        try:
            hist_dates = list_snapshot_dates(symbol, client)
        except Exception:
            hist_dates = []

        lookback_start = today - timedelta(days=lookback_days)
        hist_dates = [d for d in hist_dates if lookback_start <= d < today]

        hist_ivs: list[float] = []
        hist_rrs: list[float] = []

        for sample_date in hist_dates:
            hist_df = _load_eod_snapshot_for_expiry(symbol, sample_date, expiry, _parquet_dir)
            if hist_df.empty:
                # Try finding the nearest expiry available on that date
                continue

            hist_spot_vals = hist_df["underlying_price"].dropna()
            if hist_spot_vals.empty:
                continue
            hist_spot = float(hist_spot_vals.iloc[0])

            iv = compute_atm_iv(hist_df, hist_spot)
            if iv is not None:
                hist_ivs.append(iv)

            hist_rr = compute_risk_reversal(hist_df)
            if hist_rr is not None:
                hist_rrs.append(hist_rr.rr)

        point = build_vol_regime_row(current_iv, current_rr, hist_ivs, hist_rrs)
        if point is None:
            continue

        rows.append(
            {
                "symbol": symbol,
                "iv_zscore": point.iv_zscore,
                "rr_zscore": point.rr_zscore,
                "current_iv": point.current_iv,
                "current_rr": point.current_rr,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["symbol", "iv_zscore", "rr_zscore"])
    return pd.DataFrame(rows)


def render_vol_regime_tab(options_dir: Path = OPTIONS_DIR) -> None:
    """Render the Vol Regime subtab."""
    client = _default_client()
    roots = client.options_filesystem.list_roots()

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        selected = st.multiselect(
            "Symbols",
            options=roots,
            default=[],
            key="vol_regime_symbols",
            help="Select tickers to plot on the vol regime chart",
        )
    with c2:
        target_dte = int(
            st.selectbox("Target DTE", _TARGET_DTE_OPTIONS, index=2, key="vol_regime_dte") or 30
        )
    with c3:
        lookback = int(
            st.selectbox("Lookback (days)", _LOOKBACK_OPTIONS, index=0, key="vol_regime_lookback")
            or 30
        )

    if not selected:
        st.info("Select one or more symbols to generate the vol regime chart.")
        return

    with st.spinner(f"Computing vol regime for {len(selected)} symbols..."):
        data = _compute_vol_regime_data(
            tuple(selected),
            target_dte,
            lookback,
            str(PARQUET_OPTIONS_DIR),
        )

    if data.empty:
        st.warning(
            "No data available for the selected symbols. "
            "Try different symbols or a shorter lookback."
        )
        return

    fig = build_vol_regime_chart(data)
    st.plotly_chart(fig, use_container_width=True)

    # Summary table
    with st.expander("Data Table"):
        st.dataframe(
            data.set_index("symbol")[["iv_zscore", "rr_zscore", "current_iv", "current_rr"]].round(
                2
            ),
            use_container_width=True,
        )
