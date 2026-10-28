"""Root selectors return persisted metadata without remote reads."""

from options_monitor.data import roots


def test_root_discovery_uses_persistent_background_snapshot(monkeypatch):
    monkeypatch.setattr(roots, "cached_roots", lambda: (["SPXW", "SPY"], True))
    assert roots.available_roots() == (["SPXW", "SPY"], True)
