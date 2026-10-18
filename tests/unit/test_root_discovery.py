"""The dashboard can render before MinIO root discovery completes."""

from concurrent.futures import Future

from options_monitor.data import roots


def test_root_discovery_returns_default_until_ready(monkeypatch) -> None:
    future: Future[list[str]] = Future()
    monkeypatch.setattr(roots, "_future", future)

    assert roots.available_roots() == (["SPXW"], False)

    future.set_result(["AAPL", "SPXW"])
    assert roots.available_roots() == (["AAPL", "SPXW"], True)
