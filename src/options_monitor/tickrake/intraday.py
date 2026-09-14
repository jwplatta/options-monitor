"""MinIO intraday index and CSV access."""

from __future__ import annotations

import json
from datetime import date
from io import StringIO
from typing import Any, cast
from urllib.parse import urlparse

import boto3
import pandas as pd
from botocore.config import Config
from mypy_boto3_s3 import S3Client

from options_monitor.tickrake.config import TickrakeConfig


class IntradayClient:
    def __init__(self, cfg: TickrakeConfig) -> None:
        self._cfg = cfg
        self._s3: S3Client = boto3.client(
            "s3",
            endpoint_url=cfg.minio_endpoint,
            aws_access_key_id=cfg.minio_access_key,
            aws_secret_access_key=cfg.minio_secret_key,
            config=Config(signature_version="s3v4"),
        )

    def fetch_index(self, root: str, provider: str = "schwab") -> dict[str, Any]:
        """Fetch the intraday index JSON for root from MinIO."""
        key = f"intraday/{provider}/{root}.json"
        resp = self._s3.get_object(Bucket=self._cfg.minio_bucket, Key=key)
        return cast(dict[str, Any], json.loads(resp["Body"].read()))

    def fetch_csv(self, uri: str, dtypes: dict[str, Any]) -> pd.DataFrame:
        """Fetch an option chain CSV from a s3:// URI and return a typed DataFrame."""
        parsed = urlparse(uri)
        key = parsed.path.lstrip("/")
        resp = self._s3.get_object(Bucket=self._cfg.minio_bucket, Key=key)
        content = resp["Body"].read().decode("utf-8")
        df = pd.read_csv(StringIO(content), dtype=dtypes)  # type: ignore[arg-type]
        df["expiration_date"] = pd.to_datetime(df["expiration_date"])
        return df

    def latest_snapshots(
        self,
        root: str,
        start_exp: date,
        end_exp: date,
        provider: str = "schwab",
    ) -> dict[date, str]:
        """Return {expiry: s3_uri} for expirations in [start_exp, end_exp]."""
        index = self.fetch_index(root, provider)
        files: list[dict[str, Any]] = index.get("intraday", {}).get("files", [])
        result: dict[date, str] = {}
        for f in files:
            exp = date.fromisoformat(str(f["expiration_date"]))
            if start_exp <= exp <= end_exp:
                result[exp] = str(f["uri"])
        return dict(sorted(result.items()))

    def list_expirations(self, root: str, provider: str = "schwab") -> list[date]:
        """Return sorted list of expiration dates currently in the intraday index."""
        index = self.fetch_index(root, provider)
        files: list[dict[str, Any]] = index.get("intraday", {}).get("files", [])
        return sorted({date.fromisoformat(str(f["expiration_date"])) for f in files})
