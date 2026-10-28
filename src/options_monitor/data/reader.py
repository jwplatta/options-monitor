"""Shared Tractatus reader and DuckDB connection for dashboard data."""

from __future__ import annotations

import os

import duckdb
from tractatus.reader import Reader

_connection = duckdb.connect(os.environ.get("DUCKDB_OPTIONS_PATH", "/tmp/duckdb_options.db"))
_connection.execute("SET memory_limit='4GB'")
_connection.execute("SET threads=2")
_connection.execute("SET preserve_insertion_order=false")
_connection.execute("SET temp_directory='/tmp/duckdb_swap'")

_reader: Reader | None = None


def get_reader() -> Reader:
    global _reader
    if _reader is None:
        _reader = Reader(conn=_connection)
    return _reader
