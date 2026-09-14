"""S3 archive access with local parquet cache."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import boto3

from options_monitor.tickrake.config import TickrakeConfig

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ArchiveClient:
    def __init__(self, cfg: TickrakeConfig) -> None:
        self._cfg = cfg
        self._options_dir = cfg.options_dir
        self._s3: S3Client = boto3.client(  # type: ignore[assignment]
            "s3",
            region_name=cfg.s3_region,
        )

    def get_root_index(self, root: str) -> dict[str, Any]:
        """Read the local ROOT.json index for root."""
        path = self._options_dir / f"{root}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())  # type: ignore[return-value]

    def get_parquet_path(self, root: str, sample_date: date) -> Path | None:
        """Return the local parquet path for sample_date, downloading from S3 if needed."""
        local_path = (
            self._options_dir
            / f"{sample_date.year:04d}"
            / f"{sample_date.month:02d}"
            / f"{sample_date.day:02d}"
            / f"{root}_samples_{sample_date.isoformat()}.parquet"
        )
        if local_path.exists():
            return local_path

        uri = self._find_parquet_uri(root, sample_date)
        if uri is None:
            return None

        self._download(uri, local_path)
        return local_path if local_path.exists() else None

    def _find_parquet_uri(self, root: str, sample_date: date) -> str | None:
        index = self.get_root_index(root)
        for entry in index.get("historical", []):
            if entry.get("sample_date") == sample_date.isoformat():
                for f in entry.get("files", []):
                    if f.get("format") == "parquet":
                        return str(f["uri"])
        return None

    def _download(self, uri: str, local_path: Path) -> None:
        parsed = urlparse(uri)
        bucket = parsed.netloc or self._cfg.s3_bucket
        key = parsed.path.lstrip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._s3.download_file(bucket, key, str(local_path))
