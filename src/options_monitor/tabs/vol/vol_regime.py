"""Vol Regime subtab: IV rank vs risk reversal rank scatter."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st
from tractatus.calc.vol import compute_risk_reversal
from tractatus.tickrake.client import TickrakeClient
from tractatus.tickrake.config import TickrakeConfig
from tractatus.tickrake.options.queries import OPTIONS_DTYPES

from options_monitor.calc.vol_regime import build_vol_regime_row, compute_atm_iv
from options_monitor.charts.vol_regime import build_vol_regime_chart
from options_monitor.config import OPTIONS_DIR, PARQUET_OPTIONS_DIR
from options_monitor.data.intraday import find_latest_snapshots
from options_monitor.data.options import (
    list_snapshot_dates,
    load_options_snapshot,
)

_TARGET_DTE_OPTIONS = [5, 15, 30, 45]
_LOOKBACK_OPTIONS = [30, 45, 60, 180, 360]


def _default_client() -> TickrakeClient:
    return TickrakeClient(TickrakeConfig.from_env())


def _date_dir(parquet_dir: Path, sample_date: date) -> Path:
    return (
        parquet_dir
        / f"{sample_date.year:04d}"
        / f"{sample_date.month:02d}"
        / f"{sample_date.day:02d}"
    )


def _available_sample_dates(
    symbol: str,
    indexed_dates: list[date],
    parquet_dir: Path,
    start_date: date,
    end_date: date,
) -> list[date]:
    """Combine published index dates with local parquets in the requested window."""
    dates = {d for d in indexed_dates if start_date <= d <= end_date}
    for days_ago in range((end_date - start_date).days + 1):
        sample_date = end_date - timedelta(days=days_ago)
        day_dir = _date_dir(parquet_dir, sample_date)
        path = day_dir / f"{symbol}_samples_{sample_date.isoformat()}.parquet"
        if path.is_file():
            dates.add(sample_date)
    return sorted(dates)


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
def _pick_expiry_from_parquet(
    symbol: str,
    sample_date: date,
    ref_date: date,
    target_dte: int,
    _parquet_dir: str,
) -> date | None:
    """Pick the closest available expiry from one historical parquet."""
    parquet_path = _date_dir(Path(_parquet_dir), sample_date) / (
        f"{symbol}_samples_{sample_date.isoformat()}.parquet"
    )
    if not parquet_path.exists():
        client = _default_client()
        result = client.options_archive.get_parquet_path(symbol, sample_date)
        if result is None:
            return None
        parquet_path = result

    try:
        with duckdb.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT expiration_date FROM read_parquet(?)",
                [str(parquet_path)],
            ).fetchall()
    except Exception:
        return None

    expirations = [date.fromisoformat(str(r[0])[:10]) for r in rows]
    return _pick_expiry(expirations, ref_date, target_dte)


@st.cache_data(ttl=300, max_entries=20)
def _load_eod_snapshot_for_expiry(
    symbol: str,
    sample_date: date,
    expiry: date,
    _parquet_dir: str,
) -> pd.DataFrame:
    """Load the last snapshot for a symbol/date/expiry from archived parquet."""
    parquet_path = _date_dir(Path(_parquet_dir), sample_date) / (
        f"{symbol}_samples_{sample_date.isoformat()}.parquet"
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
        with duckdb.connect() as conn:
            df = conn.execute(
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

    df = df.astype({col: dtype for col, dtype in OPTIONS_DTYPES.items() if col in df.columns})
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=20)
def _load_daily_snapshots_for_expiry(
    symbol: str,
    sample_date: date,
    expiry: date,
    parquet_dir: str,
) -> list[pd.DataFrame]:
    """Load the first chain at/after 10:30 ET and the day's last chain."""
    parquet_path = _date_dir(Path(parquet_dir), sample_date) / (
        f"{symbol}_samples_{sample_date.isoformat()}.parquet"
    )
    if not parquet_path.exists():
        client = _default_client()
        result = client.options_archive.get_parquet_path(symbol, sample_date)
        if result is None:
            return []
        parquet_path = result

    expiry_str = expiry.isoformat()
    try:
        with duckdb.connect() as conn:
            df = conn.execute(
                """
                WITH selected_times AS (
                    SELECT
                        MIN(sampled_at) FILTER (
                            WHERE CAST(sampled_at AT TIME ZONE 'America/New_York' AS TIME)
                                  >= TIME '10:30:00'
                        ) AS after_open,
                        MAX(sampled_at) AS last_sample
                    FROM read_parquet(?)
                    WHERE expiration_date = ?
                )
                SELECT t.*
                FROM read_parquet(?) t, selected_times s
                WHERE t.expiration_date = ?
                  AND t.sampled_at IN (s.after_open, s.last_sample)
                ORDER BY t.sampled_at
                """,
                [str(parquet_path), expiry_str, str(parquet_path), expiry_str],
            ).df()
    except Exception:
        return []

    if df.empty:
        return []

    df = df.astype({col: dtype for col, dtype in OPTIONS_DTYPES.items() if col in df.columns})
    df["contract_type"] = df["contract_type"].str.upper()
    return [frame for _, frame in df.groupby("sampled_at", sort=True)]


@st.cache_data(ttl=300, max_entries=10)
def _compute_vol_regime_data(
    symbols: tuple[str, ...],
    target_dte: int,
    lookback_days: int,
    _parquet_dir: str,
) -> pd.DataFrame:
    """Compute vol regime percentiles for all symbols."""
    today = date.today()
    client = _default_client()
    rows: list[dict[str, object]] = []

    for symbol in symbols:
        # The root JSON can lag behind local parquet publication.
        try:
            indexed_dates = list_snapshot_dates(symbol, client)
        except Exception:
            indexed_dates = []
        hist_dates = _available_sample_dates(
            symbol,
            indexed_dates,
            Path(_parquet_dir),
            today - timedelta(days=lookback_days),
            today,
        )
        if not hist_dates:
            continue

        # The "current" snapshot is either today's intraday or the most
        # recent archived date (handles weekends / holidays gracefully).
        current_date = hist_dates[-1]  # most recent archived date

        # Try live intraday first — if available it's fresher
        current_expiry_df: pd.DataFrame | None = None
        expiry: date | None = None
        try:
            current_snaps = find_latest_snapshots(
                symbol,
                today,
                target_dte + 15,
            )
        except Exception:
            current_snaps = {}

        if current_snaps:
            expiry = _pick_expiry(
                list(current_snaps.keys()),
                today,
                target_dte,
            )
            if expiry is not None:
                snap_uri = current_snaps.get(expiry)
                if snap_uri is None:
                    by_dte = sorted(
                        current_snaps.keys(),
                        key=lambda e: abs((e - today).days - target_dte),
                    )
                    for exp in by_dte:
                        if exp in current_snaps:
                            expiry = exp
                            snap_uri = current_snaps[exp]
                            break
                if snap_uri is not None:
                    try:
                        raw = load_options_snapshot(snap_uri)
                        filtered = _filter_snapshot_to_expiry(raw, expiry)
                        if not filtered.empty:
                            current_expiry_df = filtered
                            current_date = today
                    except Exception:
                        pass

        # Fallback: use most recent archived EOD snapshot
        if current_expiry_df is None:
            current_date = hist_dates[-1]
            if current_date < today - timedelta(days=3):
                continue
            # We need an expiry — scan the archived parquet for available ones
            expiry = _pick_expiry_from_parquet(
                symbol,
                current_date,
                current_date,
                target_dte,
                _parquet_dir,
            )
            if expiry is None:
                continue
            current_expiry_df = _load_eod_snapshot_for_expiry(
                symbol,
                current_date,
                expiry,
                _parquet_dir,
            )
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

        # Build historical IV and RR series from two snapshots per date.
        # Each historical date picks its own nearest-to-target-DTE expiry
        # (the same fixed expiry often didn't exist weeks ago).
        lookback_start = current_date - timedelta(days=lookback_days)
        lookback_dates = [d for d in hist_dates if lookback_start <= d < current_date]
        history_through = max(lookback_dates) if lookback_dates else None

        hist_ivs: list[float] = []
        hist_rrs: list[float] = []

        for sample_date in lookback_dates:
            hist_expiry = _pick_expiry_from_parquet(
                symbol,
                sample_date,
                sample_date,
                target_dte,
                _parquet_dir,
            )
            if hist_expiry is None:
                continue

            hist_frames = _load_daily_snapshots_for_expiry(
                symbol,
                sample_date,
                hist_expiry,
                _parquet_dir,
            )
            for hist_df in hist_frames:
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
        if point is None or expiry is None:
            continue

        rows.append(
            {
                "symbol": symbol,
                "iv_rank": point.iv_rank,
                "rr_rank": point.rr_rank,
                "current_iv": point.current_iv,
                "current_rr": point.current_rr,
                "sample_date": current_date,
                "expiration_date": expiry,
                "actual_dte": (expiry - current_date).days,
                "iv_history_count": len(hist_ivs),
                "rr_history_count": len(hist_rrs),
                "history_through": history_through,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "symbol",
                "iv_rank",
                "rr_rank",
                "current_iv",
                "current_rr",
                "sample_date",
                "expiration_date",
                "actual_dte",
                "iv_history_count",
                "rr_history_count",
                "history_through",
            ]
        )
    return pd.DataFrame(rows)


def render_vol_regime_tab(options_dir: Path = OPTIONS_DIR) -> None:
    """Render the Vol Regime subtab."""
    client = _default_client()
    roots = client.options_filesystem.list_roots()

    # Streamlit's multiselect inserts a built-in "Select all" as its first
    # dropdown option. Hide that option only while this picker is open.
    st.html(
        """<style>
        body:has(.st-key-vol_regime_symbols input[aria-expanded="true"])
        ul[data-testid="stSelectboxVirtualDropdown"] li[role="option"]:first-child {
            display: none;
        }
        </style>"""
    )

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        selected = st.multiselect(
            "Symbols",
            options=roots,
            default=[],
            key="vol_regime_symbols",
            max_selections=20,
            help="Select tickers to plot on the vol regime chart",
        )
    with c2:
        target_dte = int(
            st.selectbox("Target DTE", _TARGET_DTE_OPTIONS, index=2, key="vol_regime_dte") or 30
        )
    with c3:
        lookback = int(
            st.selectbox(
                "Lookback (days)",
                _LOOKBACK_OPTIONS,
                index=4,
                key="vol_regime_lookback",
                help=(
                    "Past calendar days used to place today's IV and risk reversal "
                    "against the first snapshot after 10:30 ET and the day's last snapshot."
                ),
            )
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
            "No current percentile data for the selected symbols. "
            "A percentile needs at least three archived snapshots within the lookback window. "
            "Try a longer lookback."
        )
        return

    fig = build_vol_regime_chart(data)
    fig.update_layout(
        title=f"Vol regime percentiles · {target_dte} DTE target · {lookback} day lookback",
        margin={"l": 60, "r": 60, "t": 70, "b": 60},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "RR = 25Δ call IV − 25Δ put IV. Today's chain is compared with each symbol's "
        "first sample after 10:30 ET and last sample on each compacted day at a similar DTE; "
        "a low RR percentile does not predict direction. Hover the quadrant labels for "
        "trade ideas."
    )

    history_gaps = data[
        data.apply(
            lambda row: (
                row["history_through"] is not None
                and (row["sample_date"] - row["history_through"]).days > 7
            ),
            axis=1,
        )
    ]
    if not history_gaps.empty:
        st.warning(
            "The historical archive ends more than 7 days before the current sample "
            "for some symbols. Their percentiles omit recent market sessions; check "
            "History Through and the observation counts in the data table."
        )

    stale_dates = sorted({d for d in data["sample_date"] if d < date.today()})
    if stale_dates:
        st.caption(
            "Archive samples are shown where recent history is insufficient. "
            "Check each symbol's sample date in the data table."
        )

    # Summary table
    with st.expander("Data Table"):
        columns = [
            "iv_rank",
            "rr_rank",
            "current_iv",
            "current_rr",
            "sample_date",
            "expiration_date",
            "actual_dte",
            "iv_history_count",
            "rr_history_count",
            "history_through",
        ]
        st.dataframe(
            data.set_index("symbol")[columns]
            .round(2)
            .rename(
                columns={
                    "iv_rank": "ATM IV percentile",
                    "rr_rank": "25Δ RR percentile",
                    "current_iv": "ATM IV (%)",
                    "current_rr": "25Δ RR (pp)",
                    "sample_date": "Sample date",
                    "expiration_date": "Expiration",
                    "actual_dte": "Actual DTE",
                    "iv_history_count": "IV samples",
                    "rr_history_count": "RR samples",
                    "history_through": "History through",
                }
            ),
            use_container_width=True,
        )
