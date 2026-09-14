"""Connection config for tickrake data sources (MinIO intraday, S3 archive)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULTS_OPTIONS = Path.home() / ".tickrake" / "data" / "options" / "schwab"


@dataclass
class TickrakeConfig:
    minio_endpoint: str
    minio_bucket: str
    minio_access_key: str
    minio_secret_key: str
    s3_bucket: str
    s3_region: str
    # Provider-specific local options dir, e.g. ~/.tickrake/data/options/schwab
    options_dir: Path

    @classmethod
    def from_env(cls, options_dir: Path | None = None) -> TickrakeConfig:
        resolved_dir = options_dir or Path(
            os.environ.get("OPTIONS_DIR", str(_DEFAULTS_OPTIONS))
        )
        return cls(
            minio_endpoint=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
            minio_bucket=os.environ.get("MINIO_BUCKET", "tickrake"),
            minio_access_key=os.environ.get("MINIO_ACCESS_KEY", ""),
            minio_secret_key=os.environ.get("MINIO_SECRET_KEY", ""),
            s3_bucket=os.environ.get("S3_BUCKET", ""),
            s3_region=os.environ.get("S3_REGION", "us-east-1"),
            options_dir=resolved_dir,
        )
