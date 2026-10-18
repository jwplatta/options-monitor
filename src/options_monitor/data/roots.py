"""Background discovery of option roots for the dashboard selector."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from options_monitor.data.reader import get_reader

_DEFAULT_ROOT = "SPXW"
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="option-roots")
_lock = Lock()
_future: Future[list[str]] | None = None


def available_roots() -> tuple[list[str], bool]:
    """Return current roots and whether the MinIO lookup has finished."""
    global _future
    with _lock:
        if _future is None:
            _future = _executor.submit(lambda: get_reader().list_roots())
        future = _future
    if not future.done():
        return [_DEFAULT_ROOT], False
    try:
        roots = future.result()
    except Exception:
        roots = []
    return (roots if roots else [_DEFAULT_ROOT]), True
