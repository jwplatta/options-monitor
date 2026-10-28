"""Shared Tractatus reader and DuckDB connection for dashboard data."""

from __future__ import annotations

import os

import duckdb
from tractatus.reader import Reader


def configure_duckdb_httpfs(conn: duckdb.DuckDBPyConnection) -> None:
    """Configure DuckDB connection to read s3:// URIs from local MinIO."""
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000").removeprefix("http://").removeprefix("https://")
    use_ssl = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000").startswith("https://")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"SET s3_endpoint='{endpoint}'")
    conn.execute("SET s3_url_style='path'")
    conn.execute(f"SET s3_use_ssl={str(use_ssl).lower()}")
    conn.execute(f"SET s3_access_key_id='{os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')}'")
    conn.execute(f"SET s3_secret_access_key='{os.environ.get('MINIO_SECRET_KEY', 'minioadmin')}'")


_connection = duckdb.connect(os.environ.get("DUCKDB_OPTIONS_PATH", "/tmp/duckdb_options.db"))
_connection.execute("SET memory_limit='4GB'")
_connection.execute("SET threads=2")
_connection.execute("SET preserve_insertion_order=false")
_connection.execute("SET temp_directory='/tmp/duckdb_swap'")
configure_duckdb_httpfs(_connection)

_reader: Reader | None = None


def get_reader() -> Reader:
    global _reader
    if _reader is None:
        _reader = Reader(conn=_connection)
    return _reader
