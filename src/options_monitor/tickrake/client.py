"""TickrakeClient — facade over intraday, archive, and filesystem sub-clients."""

from __future__ import annotations

from options_monitor.tickrake.archive import ArchiveClient
from options_monitor.tickrake.config import TickrakeConfig
from options_monitor.tickrake.filesystem import FilesystemClient
from options_monitor.tickrake.intraday import IntradayClient


class TickrakeClient:
    def __init__(self, cfg: TickrakeConfig | None = None) -> None:
        _cfg = cfg or TickrakeConfig.from_env()
        self.intraday = IntradayClient(_cfg)
        self.archive = ArchiveClient(_cfg)
        self.filesystem = FilesystemClient(_cfg)
