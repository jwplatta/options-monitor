"""Options chain snapshot loader."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st
from tractatus.tickrake.client import TickrakeClient
from tractatus.tickrake.config import TickrakeConfig

_DUCKDB_CONN = duckdb.connect("/tmp/duckdb_options.db")
_DUCKDB_CONN.execute("SET memory_limit='4GB'")
_DUCKDB_CONN.execute("SET threads=2")
_DUCKDB_CONN.execute("SET preserve_insertion_order=false")
_DUCKDB_CONN.execute("SET temp_directory='/tmp/duckdb_swap'")

_OPTIONS_DTYPES: dict[str, Any] = {
    "strike": "float64",
    "open_interest": "float64",
    "gamma": "float64",
    "delta": "float64",
    "theta": "float64",
    "vega": "float64",
    "theoretical_volatility": "float64",
    "underlying_price": "float64",
    "volatility": "float64",
    "mark": "float64",
    "bid": "float64",
    "ask": "float64",
    "last": "float64",
    "last_size": "float64",
    "total_volume": "float64",
}

_OPTIONS_PROVIDER = "schwab"


def _default_client() -> TickrakeClient:
    return TickrakeClient(TickrakeConfig.from_env())


@st.cache_data(ttl=300)
def list_expirations(
    symbol: str,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return sorted list of expiration dates from the live intraday index."""
    client = _client or _default_client()
    return client.options_intraday.list_expirations(symbol)


@st.cache_data(ttl=300)
def list_snapshot_dates(
    symbol: str,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return sorted list of historical sample dates with archived data for symbol."""
    client = _client or _default_client()
    return client.options_filesystem.list_sample_dates(symbol)


@st.cache_data(ttl=300)
def list_snapshot_dates_for_expiry(
    symbol: str,
    expiry: date,
    _client: TickrakeClient | None = None,
) -> list[date]:
    """Return sorted list of sample dates with snapshots for the given expiry."""
    client = _client or _default_client()
    return client.options_filesystem.list_sample_dates_for_expiry(symbol, expiry)


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _client: TickrakeClient | None = None,
) -> dict[date, str]:
    """Return {expiry_date: s3_uri} for expirations in the intraday window."""
    target_start = start_date if include_0dte else start_date + timedelta(days=1)
    target_end = start_date + timedelta(days=days_out)
    if target_end < target_start:
        return {}
    client = _client or _default_client()
    return client.options_intraday.latest_snapshots(symbol, target_start, target_end)


@st.cache_data(ttl=30)
def find_all_snapshots_for_expiry(
    symbol: str,
    expiry: date,
    _client: TickrakeClient | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all (fetch_datetime, path) pairs for a given expiry across all local dates."""
    client = _client or _default_client()
    return client.options_filesystem.scan_all_snapshots_for_expiry(symbol, expiry)


@st.cache_data(ttl=30)
def find_snapshots_for_expiry_on_date(
    symbol: str,
    expiry: date,
    sample_date: date,
    _client: TickrakeClient | None = None,
) -> list[tuple[datetime, Path]]:
    """Return all snapshots for a given symbol/expiry on sample_date, sorted by time."""
    client = _client or _default_client()
    return client.options_filesystem.scan_snapshots_for_expiry(symbol, expiry, sample_date)


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
    return client.options_filesystem.list_expirations_in_window_on_date(
        symbol, sample_date, target_start, target_end
    )


# ---------------------------------------------------------------------------
# Parquet / DuckDB access — historical dates only (sample_date < today)
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
    return client.options_archive.get_parquet_path(symbol, sample_date)


@st.cache_data(ttl=300)
def find_historical_snapshot_times(expiry: date, parquet_path: Path) -> list[datetime]:
    """Return sorted distinct sampled_at datetimes for an expiry from a parquet file."""
    expiry_str = expiry.isoformat()
    result = _DUCKDB_CONN.execute(
        "SELECT DISTINCT sampled_at FROM read_parquet(?)"
        " WHERE expiration_date = ? ORDER BY sampled_at",
        [str(parquet_path), expiry_str],
    ).fetchall()
    return [datetime.fromisoformat(str(row[0])) for row in result]


@st.cache_data(ttl=300, max_entries=10)
def load_historical_snapshot(
    symbol: str, expiry: date, sampled_at: datetime, parquet_path: Path
) -> pd.DataFrame:
    """Load a single snapshot for one expiry and sampled_at from a parquet file."""
    expiry_str = expiry.isoformat()
    sampled_at_str = sampled_at.isoformat()
    df = _DUCKDB_CONN.execute(
        "SELECT * FROM read_parquet(?)"
        " WHERE expiration_date = ?"
        " AND CAST(sampled_at AS TIMESTAMPTZ) = CAST(? AS TIMESTAMPTZ)",
        [str(parquet_path), expiry_str, sampled_at_str],
    ).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=10)
def load_historical_expiry(
    symbol: str, expiry: date, sample_date: date, parquet_path: Path
) -> pd.DataFrame:
    """Load all snapshots for one expiry on one historical date from a parquet file."""
    expiry_str = expiry.isoformat()
    df = _DUCKDB_CONN.execute(
        "SELECT * FROM read_parquet(?) WHERE expiration_date = ? ORDER BY sampled_at",
        [str(parquet_path), expiry_str],
    ).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=5)
def load_historical_lookback(
    symbol: str,
    parquet_glob: str,
    expiry_range: tuple[date, date],
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled historical data across multiple parquet files via DuckDB glob."""
    start_str = expiry_range[0].isoformat()
    end_str = expiry_range[1].isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT *,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE expiration_date BETWEEN '{start_str}' AND '{end_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, expiration_date, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT * EXCLUDE (interval_bucket, rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at, expiration_date
    """
    df = _DUCKDB_CONN.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=5)
def load_historical_sample_window(
    symbol: str,
    parquet_glob: str,
    sample_start: date,
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled historical data across parquet files filtered by sample date."""
    start_str = sample_start.isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT sampled_at, strike, volatility, open_interest,
                   underlying_price, expiration_date, contract_type,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE CAST(sampled_at AS TIMESTAMPTZ) >= TIMESTAMPTZ '{start_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, expiration_date, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT sampled_at, strike, volatility, open_interest,
               underlying_price, expiration_date, contract_type
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at, expiration_date
    """
    df = _DUCKDB_CONN.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=300, max_entries=5)
def load_historical_expiry_lookback(
    symbol: str,
    expiry: date,
    parquet_glob: str,
    interval_minutes: int,
) -> pd.DataFrame:
    """Load downsampled data for a single expiry across multiple parquet files."""
    expiry_str = expiry.isoformat()
    query = f"""
        WITH bucketed AS (
            SELECT *,
                epoch_ms(
                    CAST(floor(epoch_ms(sampled_at) / ({interval_minutes} * 60000))
                    * ({interval_minutes} * 60000) AS BIGINT)
                ) AS interval_bucket
            FROM read_parquet('{parquet_glob}')
            WHERE expiration_date = '{expiry_str}'
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY interval_bucket, strike, contract_type
                    ORDER BY sampled_at DESC
                ) AS rn
            FROM bucketed
        )
        SELECT * EXCLUDE (interval_bucket, rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY sampled_at
    """
    df = _DUCKDB_CONN.execute(query).df()
    df = df.astype({col: dtype for col, dtype in _OPTIONS_DTYPES.items() if col in df.columns})
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df["contract_type"] = df["contract_type"].str.upper()
    return df


@st.cache_data(ttl=30)
def load_options_snapshot(
    path_or_uri: Path | str,
    _client: TickrakeClient | None = None,
) -> pd.DataFrame:
    """Load a single options snapshot from a local path or s3:// URI."""
    if isinstance(path_or_uri, str) and path_or_uri.startswith("s3://"):
        client = _client or _default_client()
        return client.options_intraday.fetch_csv(path_or_uri, _OPTIONS_DTYPES)
    path = Path(path_or_uri) if isinstance(path_or_uri, str) else path_or_uri
    if not path.exists():
        raise FileNotFoundError(f"Options snapshot not found: {path}")
    df = pd.read_csv(path, dtype=_OPTIONS_DTYPES)  # type: ignore[arg-type]
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    return df
