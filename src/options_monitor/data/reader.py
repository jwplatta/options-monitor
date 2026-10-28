"""Shared Tractatus CacheReader and DuckDB connection for dashboard data."""

from __future__ import annotations

import os

import duckdb
from tractatus.reader import CacheReader, ReaderConfig


def configure_duckdb_httpfs(conn: duckdb.DuckDBPyConnection) -> None:
    """Configure DuckDB connection to read s3:// URIs from local MinIO.

    Used for ad-hoc duckdb.connect() calls in tab files that don't go through CacheReader.
    """
    CacheReader._configure_conn(conn, ReaderConfig.load())


_connection = duckdb.connect(os.environ.get("DUCKDB_OPTIONS_PATH", "/tmp/duckdb_options.db"))
_connection.execute("SET memory_limit='4GB'")
_connection.execute("SET threads=2")
_connection.execute("SET preserve_insertion_order=false")
_connection.execute("SET temp_directory='/tmp/duckdb_swap'")

_reader: CacheReader | None = None


def get_reader() -> CacheReader:
    global _reader
    if _reader is None:
        _reader = CacheReader(conn=_connection)
    return _reader
