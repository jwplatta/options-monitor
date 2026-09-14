"""Environment-variable-backed path configuration for options_monitor."""

from __future__ import annotations

import os
from pathlib import Path

_HOME = Path.home()
_TICKRAKE = _HOME / ".tickrake" / "data"

DATA_DIR: Path = Path(os.getenv("OPTIONS_MONITOR_DATA_DIR", str(_TICKRAKE)))
# DASHBOARD.md specifies "ibkr-api" as the provider, but the actual data directory
# on disk is "ibkr-paper". Override via OPTIONS_MONITOR_CANDLE_DIR env var if needed.
CANDLE_DIR: Path = Path(
    os.getenv("OPTIONS_MONITOR_CANDLE_DIR", str(_TICKRAKE / "history" / "ibkr-paper"))
)
OPTIONS_DIR: Path = Path(
    os.getenv("OPTIONS_MONITOR_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
SCHWAB_CANDLE_DIR: Path = Path(
    os.getenv("OPTIONS_MONITOR_SCHWAB_CANDLE_DIR", str(_TICKRAKE / "history" / "schwab"))
)
PARQUET_OPTIONS_DIR: Path = Path(
    os.getenv("OPTIONS_MONITOR_OPTIONS_DIR", str(_TICKRAKE / "options" / "schwab"))
)
