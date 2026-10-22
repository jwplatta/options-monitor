"""Comparable 30-DTE skew curves, persistence, and latest-chain selection."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from options_monitor.calc.vol_skew_history import historical_band, otm_skew_points
from options_monitor.charts.vol_skew_history import build_vol_skew_history_chart
from options_monitor.data.sqlite_cache import cache_path
from options_monitor.data.vol_skew_cache import SkewCurveStore
from options_monitor.tabs.vol import skew_history


def test_otm_skew_uses_puts_below_spot_calls_above_and_atm_average() -> None:
    frame = pd.DataFrame(
        {
            "strike": [90, 90, 100, 100, 110, 110],
            "contract_type": ["put", "call", "put", "call", "call", "put"],
            "volatility": [25, 99, 22, 20, 23, 99],
        }
    )
    assert otm_skew_points(frame, 100) == [
        (pytest.approx(-0.1), 25.0),
        (0.0, 21.0),
        (pytest.approx(0.1), 23.0),
    ]


def test_historical_band_does_not_extrapolate_wings() -> None:
    grid = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
    curves = [[(-0.1, base), (0.1, base)] for base in [20.0, 30.0, 40.0]]
    lower, median, upper, counts = historical_band(curves, grid)
    assert np.isnan(lower[0]) and np.isnan(upper[-1])
    assert (lower[2], median[2], upper[2]) == pytest.approx((22.0, 30.0, 38.0))
    assert counts.tolist() == [0, 3, 3, 3, 0]


def test_skew_cache_uses_shared_database_and_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "monitor"))
    assert cache_path() == tmp_path / "monitor" / "options_monitor_cache.sqlite3"
    source = tmp_path / "SPY.parquet"
    source.write_bytes(b"first source")
    sample_date = date(2026, 10, 16)
    points = [(-0.1, 25.0), (0.1, 20.0)]
    with SkewCurveStore() as store:
        assert store.get("SPY", sample_date, 30) is None
        store.put("SPY", sample_date, 30, source, points)
    with SkewCurveStore() as store:
        assert store.get("SPY", sample_date, 30) == points
        assert store.get("SPY", sample_date, 45) is None
    source.write_bytes(b"corrected source is larger")
    with SkewCurveStore() as store:
        assert store.get("SPY", sample_date, 30) is None


def test_historical_curves_reuse_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "GLD.parquet"
    source.write_bytes(b"historical parquet")
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path / "monitor"))
    reader = MagicMock()
    reader.get_parquet.return_value = source
    monkeypatch.setattr(skew_history, "get_reader", lambda: reader)
    frame = pd.DataFrame(
        {
            "strike": [90, 110],
            "volatility": [25, 20],
            "contract_type": ["PUT", "CALL"],
            "underlying_price": [100, 100],
        }
    )
    archived = MagicMock(return_value=(frame, date(2026, 11, 15)))
    monkeypatch.setattr(skew_history, "_archived_snapshot", archived)
    sample_date = date(2026, 10, 16)

    first = skew_history._historical_curves("GLD", [sample_date])
    second = skew_history._historical_curves("GLD", [sample_date])
    assert first == second
    assert len(first) == 1
    reader.get_parquet.assert_called_once_with("GLD", sample_date)
    archived.assert_called_once_with(source, sample_date)


def test_latest_chain_prefers_current_intraday(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 10, 16)
    expiry = today + timedelta(days=31)
    frame = pd.DataFrame(
        {
            "expiration_date": [expiry],
            "underlying_price": [100],
            "strike": [100],
            "quote_at": ["2026-10-16T19:55:00Z"],
        }
    )
    reader = MagicMock()
    reader.latest_snapshots.return_value = {expiry: "s3://latest"}
    reader.load_intraday_snapshot.return_value = frame
    monkeypatch.setattr(skew_history, "get_reader", lambda: reader)
    result, sample_date, selected_expiry = skew_history._latest_chain(
        "SPY", today, [today - timedelta(days=1)]
    )
    assert result.equals(frame)
    assert (sample_date, selected_expiry) == (today, expiry)
    reader.get_parquet.assert_not_called()


def test_latest_chain_uses_quote_date_on_weekend(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 10, 18)
    friday = date(2026, 10, 16)
    expiry = date(2026, 11, 20)
    reader = MagicMock()
    reader.latest_snapshots.return_value = {expiry: "s3://latest"}
    reader.load_intraday_snapshot.return_value = pd.DataFrame(
        {
            "expiration_date": [expiry],
            "underlying_price": [100],
            "quote_at": ["2026-10-16T20:02:36Z"],
        }
    )
    monkeypatch.setattr(skew_history, "get_reader", lambda: reader)
    _, sample_date, _ = skew_history._latest_chain("SPY", today, [friday])
    assert sample_date == friday


def test_archived_snapshot_chooses_nearest_expiry_and_last_time(tmp_path: Path) -> None:
    sample_date = date(2026, 10, 16)
    selected_expiry = date(2026, 11, 16)
    other_expiry = date(2026, 12, 18)
    path = tmp_path / "SPY.parquet"
    pd.DataFrame(
        {
            "sampled_at": pd.to_datetime(
                ["2026-10-16T14:35:00Z", "2026-10-16T19:55:00Z", "2026-10-16T19:55:00Z"],
                utc=True,
            ),
            "expiration_date": [selected_expiry, selected_expiry, other_expiry],
            "strike": [95.0, 100.0, 100.0],
            "volatility": [25.0, 20.0, 30.0],
            "contract_type": ["PUT", "CALL", "CALL"],
            "underlying_price": [100.0, 100.0, 100.0],
        }
    ).to_parquet(path)
    frame, expiry = skew_history._archived_snapshot(path, sample_date)
    assert expiry == selected_expiry
    assert frame["strike"].tolist() == [100.0]


def test_chart_has_current_line_historical_band_and_spot() -> None:
    curve = [(-0.1, 25.0), (0.0, 20.0), (0.1, 22.0)]
    fig = build_vol_skew_history_chart(curve, [curve] * 3, 100.0, 10, "SPY", 30)
    assert [trace.name for trace in fig.data][-3:] == [
        "Historical 10th–90th percentile",
        "Historical median",
        "Latest chain",
    ]
    assert list(fig.data[-1].x) == pytest.approx([90.0, 100.0, 110.0])
    assert len(fig.layout.shapes) == 1
