"""Root loading is local and synchronous from committed configuration."""

from options_monitor.data import roots


def test_roots_are_available_without_background_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path))
    items, ready = roots.available_roots()
    assert ready
    assert {"SPXW", "SPY", "QQQ", "IWM"}.issubset(items)
