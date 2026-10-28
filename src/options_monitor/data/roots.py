"""Persistent option-root discovery on the shared dashboard worker."""

from options_monitor.data.vol_regime_jobs import cached_roots


def available_roots() -> tuple[list[str], bool]:
    """Return the last successful metadata snapshot without waiting for MinIO."""
    return cached_roots()
