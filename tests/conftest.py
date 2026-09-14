"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pandas as pd
import pytest
import requests

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def candle_dir() -> Path:
    """Local fixture candle CSVs — do not point at ~/.tickrake."""
    return _FIXTURES / "candles"


@pytest.fixture()
def spxw_opts() -> pd.DataFrame:
    """Small SPXW parquet fixture — one snapshot, NTM strikes, both sides."""
    parquet = _FIXTURES / "options" / "schwab" / "2026" / "04" / "14" / "SPXW_samples_2026-04-14.parquet"
    if not parquet.exists():
        pytest.skip("SPXW fixture parquet not available")
    return pd.read_parquet(parquet)


def _app_path() -> Path:
    """Return absolute path to app.py."""
    return Path(__file__).parent.parent / "src" / "options_monitor" / "app.py"


@pytest.fixture(scope="session")
def streamlit_server() -> Generator[str, None, None]:
    """Start a Streamlit server on port 8502 for the test session."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(_app_path()),
            "--server.port=8502",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            "--server.runOnSave=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8502/_stcore/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        proc.kill()
        raise RuntimeError("Streamlit server did not start within 30 seconds")

    yield "http://localhost:8502"

    proc.terminate()
    proc.wait(timeout=10)
