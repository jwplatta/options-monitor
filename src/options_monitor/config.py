"""Environment-variable-backed path configuration for options_monitor."""

from __future__ import annotations

import os
from pathlib import Path

_HOME = Path.home()
_TICKRAKE_HOME: Path = Path(os.getenv("TICKRAKE_HOME", str(_HOME / ".tickrake")))
_TICKRAKE = _TICKRAKE_HOME / "data"

DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(_TICKRAKE)))
# DASHBOARD.md specifies "ibkr-api" as the provider, but the actual data directory
# on disk is "ibkr-paper". Override via CANDLE_DIR env var if needed.
CANDLE_DIR: Path = Path(
    os.getenv("CANDLE_DIR", str(_TICKRAKE / "history" / "ibkr-paper"))
)
OPTIONS_DIR: Path = Path(
    os.getenv("OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
SCHWAB_CANDLE_DIR: Path = Path(
    os.getenv("SCHWAB_CANDLE_DIR", str(_TICKRAKE / "history" / "schwab"))
)
PARQUET_OPTIONS_DIR: Path = Path(
    os.getenv("OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
