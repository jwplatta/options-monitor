"""Options chain snapshot loader."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from tractatus.tickrake.client import TickrakeClient
from tractatus.tickrake.config import TickrakeConfig

from options_monitor.data.intraday import IntradayStore, _default_store

__all__ = [
    "load_options_snapshot",
    # archive / filesystem
    "list_snapshot_dates",
    "list_snapshot_dates_for_expiry",
    "find_all_snapshots_for_expiry",
    "find_snapshots_for_expiry_on_date",
    "list_expirations_for_window_on_date",
    "parquet_path_for_date",
    # historical archive query wrappers
    "find_historical_snapshot_times",
    "load_historical_snapshot",
    "load_historical_expiry",
    "load_historical_lookback",
    "load_historical_sample_window",
    "load_historical_expiry_lookback",
    # compound archive helpers
    "load_latest_archived_window",
    "list_expirations_from_archive",
    "load_latest_archived_single_expiry",
]

_OPTIONS_PROVIDER = "schwab"


def _default_client() -> TickrakeClient:
    return TickrakeClient(TickrakeConfig.from_env())


# ---------------------------------------------------------------------------
# Intraday snapshot loader — handles s3:// URIs and local paths
# ---------------------------------------------------------------------------


@st.cache_data(ttl=30)
def load_options_snapshot(
    path_or_uri: Path | str,
    _store: IntradayStore | None = None,
) -> pd.DataFrame:
    """Load a single options snapshot from a local path or s3:// URI."""
    if isinstance(path_or_uri, str) and path_or_uri.startswith("s3://"):
        store = _store or _default_store()
        return store.fetch_csv(path_or_uri)
    path = Path(path_or_uri) if isinstance(path_or_uri, str) else path_or_uri
    if not path.exists():
        raise FileNotFoundError(f"Options snapshot not found: {path}")
    from tractatus.tickrake.options.queries import OPTIONS_DTYPES

    df = pd.read_csv(path, dtype=OPTIONS_DTYPES)
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df


# ---------------------------------------------------------------------------
# Filesystem scanning — delegates to TickrakeClient.options_filesystem
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def list_snapshot_dates(
    symbol: str,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return sorted list of historical sample dates with archived data for symbol."""
    client = _client or _default_client()
    return client.options_filesystem.list_sample_dates(symbol)  # type: ignore[no-any-return]


@st.cache_data(ttl=300)
def list_snapshot_dates_for_expiry(
    symbol: str,
    expiry: date,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return sorted list of sample dates with snapshots for the given expiry."""
    client = _client or _default_client()
    return client.options_filesystem.list_sample_dates_for_expiry(symbol, expiry)  # type: ignore[no-any-return]


@st.cache_data(ttl=30)
def find_all_snapshots_for_expiry(
    symbol: str,
    expiry: date,
    _client: TickrakeClient | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all (fetch_datetime, path) pairs for a given expiry across all local dates."""
    client = _client or _default_client()
    return client.options_filesystem.scan_all_snapshots_for_expiry(symbol, expiry)  # type: ignore[no-any-return]


@st.cache_data(ttl=30)
def find_snapshots_for_expiry_on_date(
    symbol: str,
    expiry: date,
    sample_date: date,
    _client: TickrakeClient | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all snapshots for a given symbol/expiry on sample_date, sorted by time."""
    client = _client or _default_client()
    return client.options_filesystem.scan_snapshots_for_expiry(symbol, expiry, sample_date)  # type: ignore[no-any-return]


@st.cache_data(ttl=300)
def list_expirations_for_window_on_date(
    symbol: str,
    sample_date: date,
    days_out: int,
    include_0dte: bool = True,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return expirations in the window that have local snapshots on sample_date."""
    target_start = sample_date if include_0dte else sample_date + timedelta(days=1)
    target_end = sample_date + timedelta(days=days_out)
    if target_end < target_start:
        return []
    client = _client or _default_client()
    return client.options_filesystem.list_expirations_in_window_on_date(  # type: ignore[no-any-return]
        symbol, sample_date, target_start, target_end
    )


# ---------------------------------------------------------------------------
# Parquet path resolution — delegates to TickrakeClient.options_archive
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300, max_entries=20)
def parquet_path_for_date(
    symbol: str,
    sample_date: date,
    _client: TickrakeClient | None = None,
) -> Path | None:
    """Return the local parquet path for symbol/date, downloading from S3 if needed.

    Returns None if not available locally or in the S3 archive.
    """
    client = _client or _default_client()
    return client.options_archive.get_parquet_path(symbol, sample_date)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Historical parquet queries — delegates to TickrakeClient.options_query
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def find_historical_snapshot_times(
    expiry: date,
    parquet_path: Path,
    _client: TickrakeClient | None = None,
) -> list[datetime]:
    """Return sorted distinct sampled_at datetimes for an expiry from a parquet file."""
    client = _client or _default_client()
    return client.options_query.list_snapshot_times(parquet_path, expiry)  # type: ignore[no-any-return]


@st.cache_data(ttl=300, max_entries=10)
def load_historical_snapshot(
    symbol: str,
    expiry: date,
    sampled_at: datetime,
    parquet_path: Path,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load a single snapshot for one expiry and sampled_at from a parquet file."""
    client = _client or _default_client()
    return client.options_query.load_snapshot(parquet_path, expiry, sampled_at)  # type: ignore[no-any-return]


@st.cache_data(ttl=300, max_entries=10)
def load_historical_expiry(
    symbol: str,
    expiry: date,
    sample_date: date,
    parquet_path: Path,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load all snapshots for one expiry on one historical date from a parquet file."""
    client = _client or _default_client()
    return client.options_query.load_expiry(parquet_path, expiry)  # type: ignore[no-any-return]


@st.cache_data(ttl=300, max_entries=5)
def load_historical_lookback(
    symbol: str,
    parquet_glob: str,
    expiry_range: tuple[date, date],
    interval_minutes: int,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load downsampled historical data across multiple parquet files via DuckDB glob."""
    client = _client or _default_client()
    return client.options_query.load_lookback(parquet_glob, expiry_range, interval_minutes)  # type: ignore[no-any-return]


@st.cache_data(ttl=300, max_entries=5)
def load_historical_sample_window(
    symbol: str,
    parquet_glob: str,
    sample_start: date,
    interval_minutes: int,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load downsampled historical data across parquet files filtered by sample date."""
    client = _client or _default_client()
    return client.options_query.load_sample_window(parquet_glob, sample_start, interval_minutes)  # type: ignore[no-any-return]


@st.cache_data(ttl=300, max_entries=5)
def load_historical_expiry_lookback(
    symbol: str,
    expiry: date,
    parquet_glob: str,
    interval_minutes: int,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load downsampled data for a single expiry across multiple parquet files."""
    client = _client or _default_client()
    return client.options_query.load_expiry_lookback(parquet_glob, expiry, interval_minutes)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Compound archive helpers — orchestrate archive + query clients
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def load_latest_archived_window(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _client: TickrakeClient | None = None,
) -> tuple[datetime, dict[date, pd.DataFrame]] | None:
    """Load the most recent archived snapshot for expirations in a window.

    The expiry window is anchored on *start_date* (typically today), not the
    archive's sample date.  This means weekends/holidays naturally have no 0DTE
    expiry and the toggle behaves identically to the live path.

    Returns (latest_sampled_at, {expiry: DataFrame}) or None if no archive exists.
    """
    client = _client or _default_client()
    sample_dates = client.options_filesystem.list_sample_dates(symbol)
    if not sample_dates:
        return None
    sample_date = sample_dates[-1]
    ppath = client.options_archive.get_parquet_path(symbol, sample_date)
    if ppath is None:
        return None
    target_start = start_date if include_0dte else start_date + timedelta(days=1)
    target_end = start_date + timedelta(days=days_out)
    if target_end < target_start:
        return None
    per_expiry_latest = client.options_query.latest_window(ppath, target_start, target_end)
    if not per_expiry_latest:
        return None
    global_latest = max(ts for _, ts in per_expiry_latest)
    frames: dict[date, pd.DataFrame] = {}
    for expiry, ts in per_expiry_latest:
        df = client.options_query.load_snapshot(ppath, expiry, ts)
        if not df.empty:
            frames[expiry] = df
    if not frames:
        return None
    return global_latest, frames


@st.cache_data(ttl=300)
def list_expirations_from_archive(
    symbol: str,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return expirations from the most recent archived parquet."""
    client = _client or _default_client()
    sample_dates = client.options_filesystem.list_sample_dates(symbol)
    if not sample_dates:
        return []
    sample_date = sample_dates[-1]
    ppath = client.options_archive.get_parquet_path(symbol, sample_date)
    if ppath is None:
        return []
    return client.options_query.list_expirations(ppath, sample_date)  # type: ignore[no-any-return]


@st.cache_data(ttl=300)
def load_latest_archived_single_expiry(
    symbol: str,
    expiry: date,
    _client: TickrakeClient | None = None,
) -> tuple[datetime, pd.DataFrame] | None:
    """Load the latest archived snapshot for a single expiry.

    Returns (sampled_at, DataFrame) or None if no archive exists.
    """
    client = _client or _default_client()
    sample_dates = client.options_filesystem.list_sample_dates(symbol)
    if not sample_dates:
        return None
    sample_date = sample_dates[-1]
    ppath = client.options_archive.get_parquet_path(symbol, sample_date)
    if ppath is None:
        return None
    times = client.options_query.list_snapshot_times(ppath, expiry)
    if not times:
        return None
    return times[-1], client.options_query.load_snapshot(ppath, expiry, times[-1])
