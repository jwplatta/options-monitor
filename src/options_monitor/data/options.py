"""Cached options snapshot and historical Parquet loaders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd
import streamlit as st
from tractatus.reader import CacheReader

from options_monitor.data.reader import configure_duckdb_httpfs, get_reader


@st.cache_data(ttl=30)
def load_options_snapshot(
    path_or_uri: Path | str, _reader: CacheReader | None = None
) -> pd.DataFrame:
    """Load live URIs through Tractatus; accept local files for pure chart callers."""
    if isinstance(path_or_uri, str) and path_or_uri.startswith("s3://"):
        return cast(pd.DataFrame, (_reader or get_reader()).load_intraday_snapshot(path_or_uri))
    path = Path(path_or_uri)
    if not path.exists():
        raise FileNotFoundError(f"Options snapshot not found: {path}")
    from tractatus.tickrake.options.queries import OPTIONS_DTYPES

    df = pd.read_csv(path, dtype=OPTIONS_DTYPES)
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df


@st.cache_data(ttl=60)
def list_snapshot_dates(symbol: str, _reader: CacheReader | None = None) -> list[date]:
    return cast(list[date], (_reader or get_reader()).list_option_sample_dates(symbol))


@st.cache_data(ttl=60)
def list_snapshot_dates_for_expiry(
    symbol: str, expiry: date, _reader: CacheReader | None = None
) -> list[date]:
    reader = _reader or get_reader()
    found: list[date] = []
    for sample_date in reader.list_option_sample_dates(symbol):
        try:
            path = reader.get_option_parquet(symbol, sample_date)
        except FileNotFoundError:
            continue
        if reader.options_query.list_snapshot_times(path, expiry):
            found.append(sample_date)
    return found


@st.cache_data(ttl=60)
def list_expirations_for_window_on_date(
    symbol: str,
    sample_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: CacheReader | None = None,
) -> list[date]:
    start = sample_date if include_0dte else sample_date + timedelta(days=1)
    end = sample_date + timedelta(days=days_out)
    if end < start:
        return []
    reader = _reader or get_reader()
    try:
        path = reader.get_option_parquet(symbol, sample_date)
    except FileNotFoundError:
        return []
    return [e for e in reader.options_query.list_expirations(path, start) if e <= end]


@st.cache_data(ttl=60, max_entries=20)
def parquet_path_for_date(
    symbol: str, sample_date: date, _reader: CacheReader | None = None
) -> Path | None:
    try:
        return (_reader or get_reader()).get_option_parquet(symbol, sample_date)  # type: ignore[no-any-return]
    except FileNotFoundError:
        return None


@st.cache_data(ttl=60)
def find_historical_snapshot_times(
    expiry: date, parquet_path: Path, _reader: CacheReader | None = None
) -> list[datetime]:
    return cast(
        list[datetime],
        (_reader or get_reader()).options_query.list_snapshot_times(parquet_path, expiry),
    )


@st.cache_data(ttl=60, max_entries=10)
def load_historical_snapshot(
    symbol: str,
    expiry: date,
    sampled_at: datetime,
    parquet_path: Path,
    _reader: CacheReader | None = None,
) -> pd.DataFrame:
    return cast(
        pd.DataFrame,
        (_reader or get_reader()).options_query.load_snapshot(parquet_path, expiry, sampled_at),
    )


@st.cache_data(ttl=300, max_entries=10)
def load_historical_expiry(
    symbol: str,
    expiry: date,
    sample_date: date,
    parquet_path: Path,
    _reader: CacheReader | None = None,
) -> pd.DataFrame:
    return cast(
        pd.DataFrame, (_reader or get_reader()).options_query.load_expiry(parquet_path, expiry)
    )


@st.cache_data(ttl=300, max_entries=5)
def load_historical_sample_window(
    symbol: str,
    sample_start: date,
    interval_minutes: int,
    columns: list[str] | None = None,
    _reader: CacheReader | None = None,
) -> pd.DataFrame:
    reader = _reader or get_reader()
    end_date = date.today()
    source_paths = reader.ensure_option_parquets(symbol, sample_start, end_date)
    if not source_paths:
        return pd.DataFrame()
    return cast(
        pd.DataFrame,
        reader.options_query.load_sample_window(
            source_paths, sample_start, interval_minutes, columns=columns
        ),
    )


@st.cache_data(ttl=300, max_entries=5)
def load_latest_historical_sample_per_date(
    symbol: str,
    sample_start: date,
    columns: list[str],
    _reader: CacheReader | None = None,
) -> pd.DataFrame:
    """Load the latest snapshot for each expiry on every available sample date."""
    reader = _reader or get_reader()
    paths = reader.ensure_option_parquets(symbol, sample_start, date.today())
    if not paths:
        return pd.DataFrame()
    selected = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
    query = f"""
        SELECT {selected},
               CAST(regexp_extract(filename, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}') AS DATE)
                   AS sample_date
        FROM read_parquet(?, filename=true)
        QUALIFY sampled_at = MAX(sampled_at) OVER (PARTITION BY filename, expiration_date)
        ORDER BY filename, expiration_date, sampled_at
    """
    with duckdb.connect() as conn:
        configure_duckdb_httpfs(conn)
        return conn.execute(query, [paths]).df()


@st.cache_data(ttl=60)
def load_latest_archived_window(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: CacheReader | None = None,
) -> tuple[datetime, dict[date, pd.DataFrame]] | None:
    reader = _reader or get_reader()
    dates = reader.list_option_sample_dates(symbol)
    if not dates:
        return None
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    if end < start:
        return None
    try:
        path = reader.get_option_parquet(symbol, dates[-1])
    except FileNotFoundError:
        return None
    latest = reader.options_query.latest_window(path, start, end)
    if not latest:
        return None
    frames = {
        expiry: df
        for expiry, ts in latest
        if not (df := reader.options_query.load_snapshot(path, expiry, ts)).empty
    }
    return (max(ts for _, ts in latest), frames) if frames else None


@st.cache_data(ttl=60)
def list_expirations_from_archive(symbol: str, _reader: CacheReader | None = None) -> list[date]:
    reader = _reader or get_reader()
    dates = reader.list_option_sample_dates(symbol)
    if not dates:
        return []
    try:
        path = reader.get_option_parquet(symbol, dates[-1])
    except FileNotFoundError:
        return []
    return cast(list[date], reader.options_query.list_expirations(path, dates[-1]))


@st.cache_data(ttl=60)
def load_latest_archived_single_expiry(
    symbol: str, expiry: date, _reader: CacheReader | None = None
) -> tuple[datetime, pd.DataFrame] | None:
    reader = _reader or get_reader()
    dates = reader.list_option_sample_dates(symbol)
    if not dates:
        return None
    try:
        path = reader.get_option_parquet(symbol, dates[-1])
    except FileNotFoundError:
        return None
    times = reader.options_query.list_snapshot_times(path, expiry)
    return (
        (times[-1], reader.options_query.load_snapshot(path, expiry, times[-1])) if times else None
    )
