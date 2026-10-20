"""The dashboard can render before MinIO root discovery completes."""

from concurrent.futures import Future

import pytest

from options_monitor.data import roots


def test_root_discovery_returns_default_until_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    future: Future[list[str]] = Future()
    monkeypatch.setattr(roots, "_future", future)
    monkeypatch.setattr(roots, "_cached_roots", ["SPXW"])
    monkeypatch.setattr(roots, "_has_loaded", False)
    monkeypatch.setattr(roots, "_last_refresh", 1.0)

    assert roots.available_roots() == (["SPXW"], False)

    future.set_result(["AAPL", "SPXW"])
    assert roots.available_roots() == (["AAPL", "SPXW"], True)


def test_root_discovery_refreshes_in_background_and_keeps_current_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh: Future[list[str]] = Future()
    submitted: list[Future[list[str]]] = [refresh]

    class Executor:
        def submit(self, _fn: object) -> Future[list[str]]:
            return submitted.pop(0)

    monkeypatch.setattr(roots, "_future", None)
    monkeypatch.setattr(roots, "_executor", Executor())
    monkeypatch.setattr(roots, "_cached_roots", ["AAPL", "SPXW"])
    monkeypatch.setattr(roots, "_has_loaded", True)
    monkeypatch.setattr(roots, "_last_refresh", 100.0)
    monkeypatch.setattr(roots, "monotonic", lambda: 100.0 + roots._REFRESH_INTERVAL_SECONDS)

    assert roots.available_roots() == (["AAPL", "SPXW"], True)
    assert roots.available_roots() == (["AAPL", "SPXW"], True)

    refresh.set_result(["AAPL", "CRWV", "SPXW"])
    assert roots.available_roots() == (["AAPL", "CRWV", "SPXW"], True)


def test_failed_refresh_keeps_last_known_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    future: Future[list[str]] = Future()
    future.set_exception(RuntimeError("MinIO unavailable"))
    monkeypatch.setattr(roots, "_future", future)
    monkeypatch.setattr(roots, "_cached_roots", ["AAPL", "CRWV", "SPXW"])
    monkeypatch.setattr(roots, "_has_loaded", True)
    monkeypatch.setattr(roots, "_last_refresh", 1.0)
    monkeypatch.setattr(roots, "monotonic", lambda: 2.0)

    assert roots.available_roots() == (["AAPL", "CRWV", "SPXW"], True)
