"""Tests for the options snapshot loader."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_monitor.data.options import (
    find_all_snapshots_for_expiry,
    find_historical_snapshot_times,
    find_latest_snapshots,
    find_snapshots_for_expiry_on_date,
    list_expirations,
    list_expirations_for_window_on_date,
    list_snapshot_dates,
    list_snapshot_dates_for_expiry,
    load_historical_expiry,
    load_historical_expiry_lookback,
    load_historical_lookback,
    load_historical_snapshot,
    load_options_snapshot,
    parquet_path_for_date,
)
from options_monitor.tickrake.client import TickrakeClient
from options_monitor.tickrake.config import TickrakeConfig
from options_monitor.tickrake.filesystem import parse_snapshot_filename


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_streamlit_caches() -> None:
    list_expirations.clear()
    list_snapshot_dates.clear()
    list_snapshot_dates_for_expiry.clear()
    list_expirations_for_window_on_date.clear()
    find_latest_snapshots.clear()
    find_all_snapshots_for_expiry.clear()
    find_snapshots_for_expiry_on_date.clear()
    load_options_snapshot.clear()
    find_historical_snapshot_times.clear()
    load_historical_snapshot.clear()
    load_historical_expiry.clear()
    load_historical_lookback.clear()
    load_historical_expiry_lookback.clear()
    parquet_path_for_date.clear()


def _make_client(options_dir: Path) -> TickrakeClient:
    """Build a TickrakeClient pointed at a temp options_dir with no real S3/MinIO."""
    cfg = TickrakeConfig(
        minio_endpoint="http://localhost:9000",
        minio_bucket="tickrake",
        minio_access_key="test",
        minio_secret_key="test",
        s3_bucket="tickrake",
        s3_region="us-east-1",
        options_dir=options_dir,
    )
    # Patch boto3 so no real connections are made
    with patch("boto3.client", return_value=MagicMock()):
        return TickrakeClient(cfg)


def _write_snapshot_csv(path: Path, underlying_price: float = 5200.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "contract_type": "CALL",
                "symbol": "SPXW",
                "strike": 5200.0,
                "expiration_date": "2026-04-18",
                "mark": 10.0,
                "bid": 9.5,
                "ask": 10.5,
                "last": 10.0,
                "last_size": 1.0,
                "open_interest": 100.0,
                "total_volume": 50.0,
                "delta": 0.5,
                "gamma": 0.01,
                "theta": -0.1,
                "vega": 0.2,
                "theoretical_volatility": 0.2,
                "underlying_price": underlying_price,
            }
        ]
    )
    df.to_csv(path, index=False)
    return path


def _write_timestamped_csv(
    options_dir: Path,
    root: str,
    expiry: str,
    fetch_dt: str,
    underlying_price: float = 5200.0,
) -> Path:
    """Write a timestamped snapshot CSV at the standard path.

    Args:
        options_dir: provider-level dir, e.g. tmp/options/schwab
        root: symbol root, e.g. "SPXW"
        expiry: ISO date string for expiration, e.g. "2026-04-18"
        fetch_dt: ISO datetime string for fetch time, e.g. "2026-04-15T09:00:00"
        underlying_price: value for underlying_price column
    """
    dt = datetime.fromisoformat(fetch_dt).replace(tzinfo=UTC)
    date_str = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
    time_str = f"{dt.hour:02d}-{dt.minute:02d}-{dt.second:02d}"
    fname = f"{root}_exp{expiry}_{date_str}_{time_str}.csv"
    path = options_dir / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}" / fname
    return _write_snapshot_csv(path, underlying_price)


def _write_root_json(options_dir: Path, root: str, sample_dates: list[str]) -> None:
    """Write a ROOT.json index with the given sample dates."""
    historical = [
        {
            "sample_date": d,
            "archived_at": f"{d}T21:00:00Z",
            "files": [
                {
                    "format": "parquet",
                    "uri": f"s3://tickrake/options/schwab/{d[:4]}/{d[5:7]}/{d[8:10]}/{root}_samples_{d}.parquet",
                    "row_count": 1000,
                }
            ],
        }
        for d in sample_dates
    ]
    payload = {"provider": "schwab", "root": root, "updated_at": "2026-04-15T22:00:00Z", "historical": historical}
    (options_dir / f"{root}.json").write_text(json.dumps(payload))


def _make_intraday_index(root: str, expirations: list[str]) -> dict[str, Any]:
    """Build an intraday index JSON dict for mock responses."""
    return {
        "provider": "schwab",
        "root": root,
        "updated_at": "2026-04-15T15:00:00Z",
        "intraday": {
            "sample_date": "2026-04-15",
            "sampled_at": "2026-04-15T15:00:00Z",
            "status": "active",
            "files": [
                {
                    "expiration_date": exp,
                    "format": "csv",
                    "uri": f"s3://tickrake/intraday/schwab/options/{root}_exp{exp}.csv",
                    "row_count": 500,
                }
                for exp in expirations
            ],
        },
    }


# ---------------------------------------------------------------------------
# parse_snapshot_filename
# ---------------------------------------------------------------------------


def test_parse_filename_valid(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp2026-04-15_2026-04-15_13-30-00.csv"
    path.touch()
    result = parse_snapshot_filename(path)
    assert result is not None
    exp_date, fetch_dt = result
    assert exp_date == date(2026, 4, 15)
    assert fetch_dt == datetime(2026, 4, 15, 13, 30, 0, tzinfo=UTC)


def test_parse_filename_too_few_parts(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp2026-04-15.csv"
    path.touch()
    assert parse_snapshot_filename(path) is None


def test_parse_filename_bad_date(tmp_path: Path) -> None:
    path = tmp_path / "SPXW_exp9999-99-99_2026-04-15_13-30-00.csv"
    path.touch()
    assert parse_snapshot_filename(path) is None


# ---------------------------------------------------------------------------
# list_expirations — reads MinIO intraday index
# ---------------------------------------------------------------------------


def test_list_expirations_deduplicated_and_sorted(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    index = _make_intraday_index("SPXW", ["2026-04-17", "2026-04-15", "2026-04-17"])
    client.intraday._s3.get_object.return_value = {  # type: ignore[attr-defined]
        "Body": _body(json.dumps(index))
    }
    result = list_expirations("SPXW", _client=client)
    assert result == [date(2026, 4, 15), date(2026, 4, 17)]


# ---------------------------------------------------------------------------
# find_latest_snapshots — reads MinIO intraday index
# ---------------------------------------------------------------------------


def test_find_latest_snapshots_returns_one_uri_per_expiry_in_window(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    index = _make_intraday_index("SPXW", ["2026-04-15", "2026-04-16", "2026-04-20"])
    client.intraday._s3.get_object.return_value = {  # type: ignore[attr-defined]
        "Body": _body(json.dumps(index))
    }
    snapshots = find_latest_snapshots(
        "SPXW", start_date=date(2026, 4, 15), days_out=1, include_0dte=True, _client=client
    )
    assert set(snapshots.keys()) == {date(2026, 4, 15), date(2026, 4, 16)}
    assert snapshots[date(2026, 4, 15)].startswith("s3://")
    assert snapshots[date(2026, 4, 16)].startswith("s3://")


def test_find_latest_snapshots_respects_include_0dte(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    index = _make_intraday_index("SPXW", ["2026-04-15", "2026-04-16"])
    client.intraday._s3.get_object.return_value = {  # type: ignore[attr-defined]
        "Body": _body(json.dumps(index))
    }

    without_0dte = find_latest_snapshots(
        "SPXW", start_date=date(2026, 4, 15), days_out=2, include_0dte=False, _client=client
    )
    find_latest_snapshots.clear()
    with_0dte = find_latest_snapshots(
        "SPXW", start_date=date(2026, 4, 15), days_out=2, include_0dte=True, _client=client
    )

    assert date(2026, 4, 15) not in without_0dte
    assert date(2026, 4, 15) in with_0dte
    assert date(2026, 4, 16) in with_0dte


def test_find_latest_snapshots_empty_window(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    result = find_latest_snapshots(
        "SPXW",
        start_date=date(2026, 4, 15),
        days_out=0,
        include_0dte=False,
        _client=client,
    )
    assert result == {}


# ---------------------------------------------------------------------------
# find_snapshots_for_expiry_on_date — filesystem scan
# ---------------------------------------------------------------------------


def test_find_snapshots_for_expiry_on_date_filters_and_orders_rows(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    first = _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-15T09:00:00")
    second = _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-15T12:00:00")
    _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-16T10:00:00")  # next day
    _write_timestamped_csv(tmp_path, "SPXW", "2026-04-19", "2026-04-15T11:00:00")  # other expiry

    snapshots = find_snapshots_for_expiry_on_date(
        "SPXW", expiry=date(2026, 4, 18), sample_date=date(2026, 4, 15), _client=client
    )
    assert snapshots == [
        (datetime(2026, 4, 15, 9, 0, 0, tzinfo=UTC), first),
        (datetime(2026, 4, 15, 12, 0, 0, tzinfo=UTC), second),
    ]


def test_find_snapshots_for_expiry_on_date_empty_when_no_files(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    result = find_snapshots_for_expiry_on_date(
        "SPXW", expiry=date(2026, 4, 18), sample_date=date(2026, 4, 15), _client=client
    )
    assert result == []


# ---------------------------------------------------------------------------
# find_all_snapshots_for_expiry — filesystem scan across all dates
# ---------------------------------------------------------------------------


def test_find_all_snapshots_for_expiry_returns_all_rows_ordered_by_time(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    first = _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-14T09:00:00")
    second = _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-14T12:00:00")
    third = _write_timestamped_csv(tmp_path, "SPXW", "2026-04-18", "2026-04-15T10:00:00")
    _write_timestamped_csv(tmp_path, "SPXW", "2026-04-19", "2026-04-15T11:00:00")  # other expiry

    snapshots = find_all_snapshots_for_expiry("SPXW", expiry=date(2026, 4, 18), _client=client)
    assert snapshots == [
        (datetime(2026, 4, 14, 9, 0, 0, tzinfo=UTC), first),
        (datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC), second),
        (datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC), third),
    ]


# ---------------------------------------------------------------------------
# list_snapshot_dates — reads ROOT.json
# ---------------------------------------------------------------------------


def test_list_snapshot_dates_returns_sorted_dates_from_root_json(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_root_json(tmp_path, "SPXW", ["2026-04-14", "2026-04-15", "2026-04-13"])

    result = list_snapshot_dates("SPXW", _client=client)
    assert result == [date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15)]


def test_list_snapshot_dates_empty_when_no_root_json(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    assert list_snapshot_dates("SPXW", _client=client) == []


# ---------------------------------------------------------------------------
# list_snapshot_dates_for_expiry — proxied from ROOT.json
# ---------------------------------------------------------------------------


def test_list_snapshot_dates_for_expiry_returns_root_json_dates(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_root_json(tmp_path, "SPXW", ["2026-04-14", "2026-04-15"])

    result = list_snapshot_dates_for_expiry("SPXW", expiry=date(2026, 4, 18), _client=client)
    assert result == [date(2026, 4, 14), date(2026, 4, 15)]


# ---------------------------------------------------------------------------
# list_expirations_for_window_on_date — filesystem scan
# ---------------------------------------------------------------------------


def test_list_expirations_for_window_on_date_anchors_to_sample_date(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_timestamped_csv(tmp_path, "SPXW", "2026-06-03", "2026-06-03T13:30:00")  # 0DTE
    _write_timestamped_csv(tmp_path, "SPXW", "2026-06-05", "2026-06-03T13:31:00")  # inside
    _write_timestamped_csv(tmp_path, "SPXW", "2026-06-10", "2026-06-03T13:32:00")  # outside window

    expiries = list_expirations_for_window_on_date(
        "SPXW", sample_date=date(2026, 6, 3), days_out=2, include_0dte=True, _client=client
    )
    assert expiries == [date(2026, 6, 3), date(2026, 6, 5)]


def test_list_expirations_for_window_on_date_excludes_0dte(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_timestamped_csv(tmp_path, "SPXW", "2026-06-03", "2026-06-03T13:30:00")
    _write_timestamped_csv(tmp_path, "SPXW", "2026-06-05", "2026-06-03T13:31:00")

    expiries = list_expirations_for_window_on_date(
        "SPXW", sample_date=date(2026, 6, 3), days_out=5, include_0dte=False, _client=client
    )
    assert date(2026, 6, 3) not in expiries
    assert date(2026, 6, 5) in expiries


# ---------------------------------------------------------------------------
# load_options_snapshot — local path
# ---------------------------------------------------------------------------


def test_load_options_snapshot_local_columns(tmp_path: Path) -> None:
    csv_path = _write_snapshot_csv(tmp_path / "snapshot.csv", underlying_price=5300.0)
    df = load_options_snapshot(csv_path)
    required = ["contract_type", "strike", "open_interest", "gamma", "underlying_price"]
    for col in required:
        assert col in df.columns
    assert df["underlying_price"].iloc[0] == 5300.0


def test_load_options_snapshot_missing_local_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Options snapshot not found"):
        load_options_snapshot(tmp_path / "missing.csv")


# ---------------------------------------------------------------------------
# load_options_snapshot — s3:// URI (MinIO)
# ---------------------------------------------------------------------------


def test_load_options_snapshot_s3_uri_fetches_from_minio(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    csv_path = _write_snapshot_csv(tmp_path / "remote.csv")
    csv_bytes = csv_path.read_bytes()
    client.intraday._s3.get_object.return_value = {  # type: ignore[attr-defined]
        "Body": _body(csv_bytes)
    }

    df = load_options_snapshot("s3://tickrake/intraday/schwab/options/SPXW_exp2026-04-18.csv", _client=client)
    assert not df.empty
    assert "strike" in df.columns


# ---------------------------------------------------------------------------
# parquet_path_for_date — local cache + S3 download
# ---------------------------------------------------------------------------


def test_parquet_path_for_date_returns_existing_local_file(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    parquet_path = (
        tmp_path / "2026" / "04" / "15" / "SPXW_samples_2026-04-15.parquet"
    )
    parquet_path.parent.mkdir(parents=True)
    parquet_path.touch()

    result = parquet_path_for_date("SPXW", date(2026, 4, 15), _client=client)
    assert result == parquet_path


def test_parquet_path_for_date_downloads_from_s3_on_cache_miss(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_root_json(tmp_path, "SPXW", ["2026-04-15"])

    local_path = tmp_path / "2026" / "04" / "15" / "SPXW_samples_2026-04-15.parquet"
    assert not local_path.exists()

    def fake_download(bucket: str, key: str, dest: str) -> None:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).touch()

    client.archive._s3.download_file.side_effect = fake_download  # type: ignore[attr-defined]

    result = parquet_path_for_date("SPXW", date(2026, 4, 15), _client=client)
    assert result is not None
    assert result.exists()
    client.archive._s3.download_file.assert_called_once()  # type: ignore[attr-defined]


def test_parquet_path_for_date_returns_none_when_not_in_root_json(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _write_root_json(tmp_path, "SPXW", ["2026-04-14"])  # no 2026-04-15

    result = parquet_path_for_date("SPXW", date(2026, 4, 15), _client=client)
    assert result is None


# ---------------------------------------------------------------------------
# Parquet / DuckDB integration tests
#
# These tests require a real parquet file on disk produced by tickrake.
# They are skipped automatically if the file is absent.
# ---------------------------------------------------------------------------

_INTEGRATION_PARQUET = (
    Path.home() / ".tickrake/data/options/schwab/2026/06/25/SPXW_samples_2026-06-25.parquet"
)
_INTEGRATION_DATE = date(2026, 6, 25)
_INTEGRATION_SYMBOL = "SPXW"


def test_parquet_path_for_date_known_good(tmp_path: Path) -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    client = _make_client(_INTEGRATION_PARQUET.parent.parent.parent.parent)
    p = parquet_path_for_date(_INTEGRATION_SYMBOL, _INTEGRATION_DATE, _client=client)
    assert p is not None
    assert p.exists()


def test_parquet_path_for_date_missing_returns_none() -> None:
    from options_monitor.tickrake.archive import ArchiveClient

    cfg = TickrakeConfig(
        minio_endpoint="",
        minio_bucket="",
        minio_access_key="",
        minio_secret_key="",
        s3_bucket="",
        s3_region="",
        options_dir=Path("/nonexistent/path"),
    )
    with patch("boto3.client", return_value=MagicMock()):
        archive = ArchiveClient(cfg)
    assert archive.get_parquet_path("SPXW", date(2099, 1, 1)) is None


def test_find_historical_snapshot_times_returns_sorted_datetimes() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))

    times = find_historical_snapshot_times(expiry, _INTEGRATION_PARQUET)
    assert len(times) > 0
    assert all(isinstance(t, datetime) for t in times)
    assert times == sorted(times)


def test_load_historical_snapshot_returns_correct_columns() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    row = duckdb.execute(
        "SELECT expiration_date, sampled_at FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert row is not None
    expiry = date.fromisoformat(str(row[0]))
    sampled_at = datetime.fromisoformat(str(row[1]))

    df = load_historical_snapshot(_INTEGRATION_SYMBOL, expiry, sampled_at, _INTEGRATION_PARQUET)
    assert not df.empty
    required = ["contract_type", "strike", "gamma", "underlying_price", "expiration_date"]
    for col in required:
        assert col in df.columns
    assert df["contract_type"].str.isupper().all()


def test_load_historical_expiry_all_rows_for_expiry() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))

    df = load_historical_expiry(
        _INTEGRATION_SYMBOL, expiry, _INTEGRATION_DATE, _INTEGRATION_PARQUET
    )
    assert not df.empty
    assert (df["expiration_date"] == pd.Timestamp(expiry)).all()
    assert df["sampled_at"].is_monotonic_increasing


def test_load_historical_lookback_interval_filtering() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    bounds = duckdb.execute(
        "SELECT MIN(expiration_date), MAX(expiration_date) FROM read_parquet(?)",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert bounds is not None
    start = date.fromisoformat(str(bounds[0]))
    end = date.fromisoformat(str(bounds[1]))
    glob = str(_INTEGRATION_PARQUET.parent / "*.parquet")

    df = load_historical_lookback(_INTEGRATION_SYMBOL, glob, (start, end), interval_minutes=30)
    assert not df.empty
    ts_ms = pd.to_datetime(df["sampled_at"], utc=True).astype("int64") // 1_000
    bucket = (ts_ms // (30 * 60 * 1_000)).rename("bucket")
    df_check = df[["expiration_date", "strike", "contract_type"]].copy()
    df_check["bucket"] = bucket.values
    assert (
        df_check.groupby(["bucket", "expiration_date", "strike", "contract_type"]).size().max() == 1
    )


def test_load_historical_expiry_lookback_single_expiry_across_dates() -> None:
    if not _INTEGRATION_PARQUET.exists():
        pytest.skip("Integration parquet file not present")
    import duckdb

    expiry_raw = duckdb.execute(
        "SELECT DISTINCT expiration_date FROM read_parquet(?) ORDER BY expiration_date LIMIT 1",
        [str(_INTEGRATION_PARQUET)],
    ).fetchone()
    assert expiry_raw is not None
    expiry = date.fromisoformat(str(expiry_raw[0]))
    glob = str(_INTEGRATION_PARQUET.parent / "*.parquet")

    df = load_historical_expiry_lookback(_INTEGRATION_SYMBOL, expiry, glob, interval_minutes=30)
    assert not df.empty
    assert (df["expiration_date"] == pd.Timestamp(expiry)).all()
    ts_ms = pd.to_datetime(df["sampled_at"], utc=True).astype("int64") // 1_000
    bucket = (ts_ms // (30 * 60 * 1_000)).rename("bucket")
    df_check = df[["strike", "contract_type"]].copy()
    df_check["bucket"] = bucket.values
    assert df_check.groupby(["bucket", "strike", "contract_type"]).size().max() == 1
    buckets = ts_ms // (30 * 60 * 1_000)
    assert buckets.is_monotonic_increasing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body(content: bytes | str) -> MagicMock:
    """Build a mock S3 Body object that returns content on .read()."""
    body = MagicMock()
    if isinstance(content, str):
        content = content.encode()
    body.read.return_value = content
    return body
