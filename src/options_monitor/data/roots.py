"""Background discovery of option roots for the dashboard selector."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from time import monotonic

from options_monitor.data.reader import get_reader

_DEFAULT_ROOT = "SPXW"
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="option-roots")
_lock = Lock()
_future: Future[list[str]] | None = None
_cached_roots = [_DEFAULT_ROOT]
_has_loaded = False
_last_refresh = 0.0
_REFRESH_INTERVAL_SECONDS = 300


def available_roots() -> tuple[list[str], bool]:
    """Return current roots and whether the MinIO lookup has finished."""
    global _cached_roots, _future, _has_loaded, _last_refresh
    with _lock:
        now = monotonic()
        if _future is not None and _future.done():
            try:
                roots = _future.result()
            except Exception:
                roots = []
            if roots:
                _cached_roots = roots
            _has_loaded = True
            _future = None

        refresh_due = not _has_loaded or now - _last_refresh >= _REFRESH_INTERVAL_SECONDS
        if _future is None and refresh_due:
            _future = _executor.submit(lambda: get_reader().list_roots())
            _last_refresh = now

        roots = list(_cached_roots)
        loaded = _has_loaded
    return roots, loaded
