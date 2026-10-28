"""Persistent source validation for Fixed Strike bucket statistics."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from options_monitor.data.fixed_strike_cache import FixedStrikeBucketStore
from options_monitor.data.sqlite_cache import cache_path
from options_monitor.tabs.vol import fixed_strike


def _stats() -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(
        [("CALL", "7-8d", "-0.01/0.01")],
        names=["contract_type", "dte_bucket", "moneyness_bucket"],
    )
    return pd.DataFrame({"iv_mean": [20.0], "iv_std": [2.5], "count": [8]}, index=index)


def test_store_persists_and_invalidates_source(tmp_path: Path) -> None:
    source = tmp_path / "SPY.parquet"
    source.write_bytes(b"first")
    db_path = tmp_path / "fixed.sqlite3"
    stats = _stats()

    with FixedStrikeBucketStore(db_path) as store:
        assert store.get("SPY", 30, 60, [source]) is None
        store.put("SPY", 30, 60, [source], stats, 5)
        cached = store.get("SPY", 30, 60, [source])
        assert cached is not None
        pd.testing.assert_frame_equal(cached[0], stats)
        assert cached[1] == 5
        assert store.get("SPY", 30, 30, [source]) is None
        assert store.get("QQQ", 30, 60, [source]) is None

    with FixedStrikeBucketStore(db_path) as store:
        cached = store.get("SPY", 30, 60, [source])
        assert cached is not None
        pd.testing.assert_frame_equal(cached[0], stats)
        source.write_bytes(b"source corrected and longer")
        assert store.get("SPY", 30, 60, [source]) is None


def test_cache_path_uses_monitor_cache_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "monitor"))
    assert cache_path() == tmp_path / "monitor" / "options_monitor_cache.sqlite3"


def test_bucket_stats_hit_skips_historical_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "SPY.parquet"
    source.write_bytes(b"source")
    reader = MagicMock()
    reader.ensure_option_parquets.return_value = [source]
    monkeypatch.setattr(fixed_strike, "get_reader", lambda: reader)
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "monitor"))
    compute = MagicMock(side_effect=AssertionError("cache hit should skip calculation"))
    monkeypatch.setattr(fixed_strike, "build_bucket_stats", compute)

    with FixedStrikeBucketStore() as store:
        store.put("SPY", 30, 60, [source], _stats(), 5)
    result = fixed_strike._load_bucket_stats.__wrapped__("SPY", 30, 60)

    pd.testing.assert_frame_equal(result, _stats())
    assert result.attrs["sample_days"] == 5
    compute.assert_not_called()


def test_bucket_stats_miss_calculates_and_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "SPY.parquet"
    source.write_bytes(b"source")
    reader = MagicMock()
    reader.ensure_option_parquets.return_value = [source]
    monkeypatch.setattr(fixed_strike, "get_reader", lambda: reader)
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "monitor"))
    frames = [pd.DataFrame({"strike": [100]})]
    sample_times = [pd.Timestamp("2026-10-15T15:00:00Z").to_pydatetime()]
    monkeypatch.setattr(fixed_strike, "_load_historical_frames", lambda *_: (frames, sample_times))
    calculated = _stats()
    compute = MagicMock(return_value=calculated)
    monkeypatch.setattr(fixed_strike, "build_bucket_stats", compute)

    result = fixed_strike._load_bucket_stats.__wrapped__("SPY", 30, 60)
    pd.testing.assert_frame_equal(result, calculated)
    compute.assert_called_once_with(frames, sample_times)

    with FixedStrikeBucketStore() as store:
        cached = store.get("SPY", 30, 60, [source])
        assert cached is not None
        pd.testing.assert_frame_equal(cached[0], calculated)


def test_historical_frames_use_shared_sample_window_loader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frame = pd.DataFrame(
        {
            "sampled_at": pd.to_datetime(["2026-10-15T15:00:00Z"], utc=True),
            "strike": [100],
        }
    )
    loader = MagicMock(return_value=frame)
    monkeypatch.setattr(fixed_strike, "load_historical_sample_window", loader)
    frames, times = fixed_strike._load_historical_frames("SPY", 30, 60)
    assert len(frames) == 1
    assert times[0].date() == date(2026, 10, 15)
    loader.assert_called_once_with("SPY", date.today() - timedelta(days=30), 60)


def test_fractional_strikes_keep_distinct_table_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    from options_monitor.tabs.vol import fixed_strike

    iv = pd.DataFrame([[30.0, 31.0]], index=[date(2026, 10, 23)], columns=[47.5, 48.0])
    zscores = pd.DataFrame([[1.0, -1.0]], index=iv.index, columns=iv.columns)
    monkeypatch.setattr(fixed_strike.st, "dataframe", lambda styled, **_: styled.to_html())
    monkeypatch.setattr(fixed_strike.st, "markdown", lambda *_args, **_kwargs: None)

    fixed_strike._render_fsv_table(iv, spot=48.0, otm_pct=5, zscore_matrix=zscores)

    assert fixed_strike._format_strike(47.5) == "47.5"
    assert fixed_strike._format_strike(48.0) == "48"
