"""Latest 30-DTE option skew against historical daily skew curves."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import streamlit as st

from options_monitor.calc.vol_skew_history import otm_skew_points
from options_monitor.charts.vol_skew_history import build_vol_skew_history_chart
from options_monitor.data.reader import configure_duckdb_httpfs, get_reader
from options_monitor.data.vol_skew_cache import SkewCurveStore

_TARGET_DTE = 30
_LOOKBACK_OPTIONS = [30, 45, 60, 180, 360]
_NEW_YORK = ZoneInfo("America/New_York")


def _closest_expiry(expirations: list[date], sample_date: date) -> date | None:
    valid = [expiry for expiry in expirations if expiry >= sample_date]
    if not valid:
        return None
    return min(valid, key=lambda expiry: abs((expiry - sample_date).days - _TARGET_DTE))


def _archived_snapshot(path: str, sample_date: date) -> tuple[pd.DataFrame, date | None]:
    """Read only the last option chain for the expiry nearest 30 DTE."""
    with duckdb.connect() as conn:
        configure_duckdb_httpfs(conn)
        expirations = [
            date.fromisoformat(str(row[0])[:10])
            for row in conn.execute(
                "SELECT DISTINCT expiration_date FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]
        expiry = _closest_expiry(expirations, sample_date)
        if expiry is None:
            return pd.DataFrame(), None
        frame = conn.execute(
            """
            WITH last_sample AS (
                SELECT MAX(sampled_at) AS sampled_at FROM read_parquet(?)
                WHERE expiration_date = ?
            )
            SELECT t.sampled_at, t.expiration_date, t.strike, t.volatility,
                   t.contract_type, t.underlying_price
            FROM read_parquet(?) t, last_sample s
            WHERE t.expiration_date = ? AND t.sampled_at = s.sampled_at
            """,
            [str(path), expiry.isoformat(), str(path), expiry.isoformat()],
        ).df()
    return frame, expiry


def _spot(snapshot: pd.DataFrame) -> float | None:
    if "underlying_price" not in snapshot:
        return None
    values = pd.to_numeric(snapshot["underlying_price"], errors="coerce").dropna()
    if values.empty:
        return None
    spot = float(values.iloc[0])
    return spot if spot > 0 else None


def _quote_date(snapshot: pd.DataFrame) -> date | None:
    """The live CSV has quote_at rather than sampled_at; trade_at may be stale."""
    if "quote_at" not in snapshot:
        return None
    quotes = pd.to_datetime(snapshot["quote_at"], errors="coerce", utc=True).dropna()
    if quotes.empty:
        return None
    return quotes.max().tz_convert(_NEW_YORK).date()


def _latest_chain(
    symbol: str, today: date, dates: list[date]
) -> tuple[pd.DataFrame, date | None, date | None]:
    """Prefer today's newest intraday chain, then a recent archived EOD chain."""
    reader = get_reader()
    try:
        snapshots = reader.latest_snapshots(symbol, today, today + timedelta(days=45))
    except Exception:
        snapshots = {}
    expiry = _closest_expiry(list(snapshots), today)
    if expiry is not None:
        try:
            frame = reader.load_intraday_snapshot(snapshots[expiry])
            frame = frame[frame["expiration_date"].astype(str).str.startswith(expiry.isoformat())]
            if not frame.empty:
                sample_date = _quote_date(frame)
                if sample_date is not None and sample_date <= today:
                    nearest = _closest_expiry(list(snapshots), sample_date)
                    if nearest is not None and nearest != expiry:
                        candidate = reader.load_intraday_snapshot(snapshots[nearest])
                        candidate = candidate[
                            candidate["expiration_date"]
                            .astype(str)
                            .str.startswith(nearest.isoformat())
                        ]
                        if not candidate.empty:
                            frame = candidate
                            expiry = nearest
                            sample_date = _quote_date(frame)
                    if (
                        sample_date is not None
                        and today - timedelta(days=3) <= sample_date <= today
                    ):
                        return frame, sample_date, expiry
        except Exception:
            pass

    if not dates or dates[-1] < today - timedelta(days=3):
        return pd.DataFrame(), None, None
    sample_date = dates[-1]
    try:
        path = reader.get_option_parquet(symbol, sample_date)
    except FileNotFoundError:
        return pd.DataFrame(), None, None
    frame, expiry = _archived_snapshot(path, sample_date)
    return frame, sample_date, expiry


def _historical_curves(symbol: str, dates: list[date]) -> list[list[tuple[float, float]]]:
    """Resolve uncached days once, then read only compact SQLite curves."""
    reader = get_reader()
    curves: list[list[tuple[float, float]]] = []
    with SkewCurveStore() as store:
        for sample_date in dates:
            points = store.get(symbol, sample_date, _TARGET_DTE)
            if points is None:
                try:
                    path = reader.get_option_parquet(symbol, sample_date)
                except FileNotFoundError:
                    continue
                try:
                    frame, _ = _archived_snapshot(path, sample_date)
                except (duckdb.Error, ValueError):
                    continue
                spot = _spot(frame)
                points = otm_skew_points(frame, spot) if spot is not None else []
                store.put(symbol, sample_date, _TARGET_DTE, path, points)
            if len(points) >= 2:
                curves.append(points)
    return curves


@st.fragment(run_every="30s")
def render_skew_history_tab() -> None:
    """Render current 30-DTE skew with a historical IV band."""
    symbol = str(st.session_state.get("global_symbol", "SPXW"))
    c1, c2 = st.columns(2)
    with c1:
        lookback = int(
            st.selectbox("Lookback (days)", _LOOKBACK_OPTIONS, index=0, key="skew_lookback")
        )
    with c2:
        strike_range_pct = float(
            st.selectbox("Strike range (±% of spot)", [5, 10, 15, 20], index=1, key="skew_range")
        )

    today = datetime.now(_NEW_YORK).date()
    reader = get_reader()
    dates = sorted(d for d in reader.list_option_sample_dates(symbol) if d <= today)
    current, sample_date, expiry = _latest_chain(symbol, today, dates)
    spot = _spot(current)
    if current.empty or spot is None or sample_date is None or expiry is None:
        st.warning(f"No recent 30-DTE option chain is available for {symbol}.")
        return
    current_points = otm_skew_points(current, spot)
    if len(current_points) < 2:
        st.warning(f"The latest {symbol} chain has too few valid IV strikes to plot a skew.")
        return

    hist_dates = [d for d in dates if sample_date - timedelta(days=lookback) <= d < sample_date]
    with st.spinner(f"Loading {symbol} historical 30-DTE skews…"):
        history = _historical_curves(symbol, hist_dates)
    fig = build_vol_skew_history_chart(
        current_points, history, spot, strike_range_pct, symbol, lookback
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)
    sampled_at = ""
    if "sampled_at" in current and not current["sampled_at"].empty:
        sampled_at = f" · sample {current['sampled_at'].iloc[0]}"
    elif "quote_at" in current and not current["quote_at"].empty:
        sampled_at = f" · latest quote {current['quote_at'].max()}"
    st.caption(
        f"Current: {sample_date}, expiry {expiry} ({(expiry - sample_date).days} DTE)"
        f"{sampled_at}. Historical band: daily closing chains nearest 30 DTE, "
        f"{len(history)} sessions. Each historical strike is aligned to its day's spot; "
        "the band shows the 10th–90th percentile where at least three sessions have data."
    )
    if len(history) < 3:
        st.info("At least three historical daily skews are needed for the shaded range.")
