"""Keep unit UI rendering independent of real storage and background workers."""

import pytest


@pytest.fixture(autouse=True)
def isolated_dashboard_metadata(monkeypatch, tmp_path):
    from options_monitor.data import roots

    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(roots, "cached_roots", lambda: (["SPXW", "SPY", "QQQ"], True))
