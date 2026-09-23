"""MinIO intraday access for live options snapshots."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

import boto3
import pandas as pd
import streamlit as st
from botocore.config import Config
from botocore.exceptions import ClientError
from tractatus.tickrake.options.queries import OPTIONS_DTYPES

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

_OPTIONS_PROVIDER = "schwab"


class IntradayStore:
    """Thin wrapper around MinIO for intraday options index access."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._bucket = bucket
        self._s3: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    @classmethod
    def from_env(cls) -> IntradayStore:
        return cls(
            endpoint=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
            bucket=os.environ.get("MINIO_BUCKET", "tickrake"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", ""),
            secret_key=os.environ.get("MINIO_SECRET_KEY", ""),
        )

    def fetch_index(self, root: str, provider: str = _OPTIONS_PROVIDER) -> dict[str, Any]:
        """Fetch the intraday index JSON for root from MinIO.

        Returns an empty dict when the key or bucket does not exist, or when
        the MinIO endpoint is unreachable.
        """
        key = f"intraday/{provider}/{root}.json"
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            logger.debug("fetch_index %s: %s (%s)", key, code, exc)
            return {}
        except Exception as exc:
            logger.debug("fetch_index %s: %s", key, exc)
            return {}
        return cast(dict[str, Any], json.loads(resp["Body"].read()))

    def fetch_csv(self, uri: str) -> pd.DataFrame:
        """Fetch an option chain CSV from an s3:// URI and return a typed DataFrame."""
        parsed = urlparse(uri)
        key = parsed.path.lstrip("/")
        resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        content = resp["Body"].read().decode("utf-8")
        df = pd.read_csv(StringIO(content), dtype=OPTIONS_DTYPES)
        df["expiration_date"] = pd.to_datetime(df["expiration_date"])
        return df

    def _latest_files(self, index: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract latest-snapshot file entries from an index, handling old and new layouts."""
        option_chains: dict[str, Any] = index.get("option_chains", {})
        latest: dict[str, Any] = option_chains.get("latest", {})
        files: list[dict[str, Any]] = (
            latest.get("files")
            or option_chains.get("files")
            or index.get("intraday", {}).get("files", [])
        )
        return files

    def latest_snapshots(
        self,
        root: str,
        start_exp: date,
        end_exp: date,
        provider: str = _OPTIONS_PROVIDER,
    ) -> dict[date, str]:
        """Return {expiry: s3_uri} for expirations in [start_exp, end_exp]."""
        index = self.fetch_index(root, provider)
        files = self._latest_files(index)
        result: dict[date, str] = {}
        for f in files:
            exp = date.fromisoformat(str(f["expiration_date"]))
            if start_exp <= exp <= end_exp:
                result[exp] = str(f["uri"])
        return dict(sorted(result.items()))

    def series_snapshots(
        self,
        root: str,
        start_exp: date,
        end_exp: date,
        provider: str = _OPTIONS_PROVIDER,
    ) -> list[dict[str, Any]]:
        """Return series entries for expirations in [start_exp, end_exp], ordered chronologically.

        Each entry contains at minimum: expiration_date, sampled_at, uri.
        Returns an empty list when no series data is available (e.g. older tickrake instances).
        """
        index = self.fetch_index(root, provider)
        series: list[dict[str, Any]] = index.get("option_chains", {}).get("series", [])
        return [
            entry
            for entry in series
            if start_exp <= date.fromisoformat(str(entry["expiration_date"])) <= end_exp
        ]

    def list_latest_uris(
        self,
        root: str,
        start_exp: date,
        end_exp: date,
        provider: str = _OPTIONS_PROVIDER,
    ) -> dict[date, str]:
        """Return {expiry: s3_uri} by listing the latest/ path prefix directly.

        Queries intraday/<provider>/options/latest/<root>_exp* without reading the index JSON.
        Returns an empty dict on error or when MinIO is unreachable.
        """
        prefix = f"intraday/{provider}/options/latest/{root}_exp"
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            result: dict[date, str] = {}
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key: str = str(obj["Key"])
                    stem = key.rsplit("/", 1)[-1].removesuffix(".csv")
                    parts = stem.split("_exp", 1)
                    if len(parts) != 2:
                        continue
                    try:
                        exp = date.fromisoformat(parts[1])
                    except ValueError:
                        continue
                    if start_exp <= exp <= end_exp:
                        result[exp] = f"s3://{self._bucket}/{key}"
            return dict(sorted(result.items()))
        except Exception as exc:
            logger.debug("list_latest_uris(%s): %s", root, exc)
            return {}

    def list_expirations(self, root: str, provider: str = _OPTIONS_PROVIDER) -> list[date]:
        """Return sorted list of expiration dates currently in the intraday index."""
        index = self.fetch_index(root, provider)
        files = self._latest_files(index)
        return sorted({date.fromisoformat(str(f["expiration_date"])) for f in files})

    def list_roots(self, provider: str = _OPTIONS_PROVIDER) -> list[str]:
        """Return sorted list of option roots available in the intraday MinIO index.

        Lists objects under the ``intraday/{provider}/`` prefix and returns the
        stem of each ``.json`` index file found (excluding special keys).
        Returns an empty list when MinIO is unreachable.
        """
        prefix = f"intraday/{provider}/"
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            roots: list[str] = []
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
                for obj in page.get("Contents", []):
                    key: str = str(obj["Key"])
                    if key.endswith(".json"):
                        stem = key[len(prefix) :].removesuffix(".json")
                        if stem:
                            roots.append(stem)
            return sorted(roots)
        except Exception as exc:
            logger.debug("list_roots(%s): %s", provider, exc)
            return []

    def updated_at(self, root: str, provider: str = _OPTIONS_PROVIDER) -> datetime | None:
        """Return the updated_at timestamp from the intraday index for root, or None."""
        index = self.fetch_index(root, provider)
        raw = index.get("updated_at")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Module-level default store (constructed from env vars)
# ---------------------------------------------------------------------------

_store_singleton: IntradayStore | None = None


def _default_store() -> IntradayStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = IntradayStore.from_env()
    return _store_singleton


# ---------------------------------------------------------------------------
# Cached public API
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def list_expirations(
    symbol: str,
    _store: IntradayStore | None = None,
) -> list[date]:
    """Return sorted list of expiration dates from the live intraday index."""
    store = _store or _default_store()
    return store.list_expirations(symbol)


@st.cache_data(ttl=30)
def find_intraday_updated_at(
    symbol: str,
    _store: IntradayStore | None = None,
) -> datetime | None:
    """Return the updated_at timestamp from the intraday index for symbol, or None."""
    store = _store or _default_store()
    return store.updated_at(symbol)


@st.cache_data(ttl=30)
def find_series_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _store: IntradayStore | None = None,
) -> list[dict[str, Any]]:
    """Return chronological series entries for the current trading day."""
    target_start = start_date if include_0dte else start_date + timedelta(days=1)
    target_end = start_date + timedelta(days=days_out)
    if target_end < target_start:
        return []
    store = _store or _default_store()
    return store.series_snapshots(symbol, target_start, target_end)


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _store: IntradayStore | None = None,
) -> dict[date, str]:
    """Return {expiry_date: s3_uri} for expirations in the intraday window."""
    target_start = start_date if include_0dte else start_date + timedelta(days=1)
    target_end = start_date + timedelta(days=days_out)
    if target_end < target_start:
        return {}
    store = _store or _default_store()
    result = store.list_latest_uris(symbol, target_start, target_end)
    if not result:
        result = store.latest_snapshots(symbol, target_start, target_end)
    return result
