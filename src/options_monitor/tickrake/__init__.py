"""Tickrake data access module — intraday (MinIO), archive (S3), and local filesystem."""

from options_monitor.tickrake.client import TickrakeClient

__all__ = ["TickrakeClient"]
