"""Tests for IntradayStore and its cached helper functions."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_monitor.data.intraday import (
    IntradayStore,
    find_intraday_updated_at,
    find_latest_snapshots,
    list_expirations,
)
from options_monitor.data.options import load_options_snapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    list_expirations.clear()
    find_intraday_updated_at.clear()
    find_latest_snapshots.clear()
    load_options_snapshot.clear()  # defined in options.py, cleared here for intraday tests


def _make_store() -> tuple[IntradayStore, MagicMock]:
    """Return (store, mock_s3) for use in tests."""
    mock_s3 = MagicMock()
    with patch("boto3.client", return_value=mock_s3):
        store = IntradayStore(
            endpoint="http://localhost:9000",
            bucket="tickrake",
            access_key="test",
            secret_key="test",
        )
    return store, mock_s3


def _body(content: bytes | str) -> MagicMock:
    body = MagicMock()
    if isinstance(content, str):
        content = content.encode()
    body.read.return_value = content
    return body


def _make_index(root: str, expirations: list[str]) -> dict[str, Any]:
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
                    "uri": f"s3://tickrake/intraday/schwab/options/SPXW_exp{exp}.csv",
                    "row_count": 500,
                }
                for exp in expirations
            ],
        },
    }


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "contract_type": "CALL",
                "strike": 5200.0,
                "expiration_date": "2026-04-18",
                "open_interest": 100.0,
                "gamma": 0.01,
                "underlying_price": 5200.0,
            }
        ]
    ).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# IntradayStore.fetch_index
# ---------------------------------------------------------------------------


def test_fetch_index_returns_parsed_json() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-18"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = store.fetch_index("SPXW")
    assert result["root"] == "SPXW"
    mock_s3.get_object.assert_called_once_with(
        Bucket="tickrake", Key="intraday/schwab/SPXW.json"
    )


def test_fetch_index_returns_empty_on_client_error() -> None:
    from botocore.exceptions import ClientError

    store, mock_s3 = _make_store()
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
    )
    assert store.fetch_index("MISSING") == {}


def test_fetch_index_returns_empty_on_connection_error() -> None:
    store, mock_s3 = _make_store()
    mock_s3.get_object.side_effect = ConnectionError("unreachable")
    assert store.fetch_index("SPXW") == {}


# ---------------------------------------------------------------------------
# IntradayStore.list_expirations
# ---------------------------------------------------------------------------


def test_list_expirations_sorted_and_deduped() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-20", "2026-04-18", "2026-04-20"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = store.list_expirations("SPXW")
    assert result == [date(2026, 4, 18), date(2026, 4, 20)]


def test_list_expirations_empty_when_minio_down() -> None:
    store, mock_s3 = _make_store()
    mock_s3.get_object.side_effect = ConnectionError("down")
    assert store.list_expirations("SPXW") == []


# ---------------------------------------------------------------------------
# IntradayStore.latest_snapshots
# ---------------------------------------------------------------------------


def test_latest_snapshots_filters_to_window() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-15", "2026-04-16", "2026-04-20"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = store.latest_snapshots("SPXW", date(2026, 4, 15), date(2026, 4, 16))
    assert set(result.keys()) == {date(2026, 4, 15), date(2026, 4, 16)}
    assert all(v.startswith("s3://") for v in result.values())


def test_latest_snapshots_empty_when_no_match() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-20"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = store.latest_snapshots("SPXW", date(2026, 4, 15), date(2026, 4, 16))
    assert result == {}


# ---------------------------------------------------------------------------
# IntradayStore.updated_at
# ---------------------------------------------------------------------------


def test_updated_at_parses_timestamp() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", [])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    ts = store.updated_at("SPXW")
    assert isinstance(ts, datetime)
    assert ts.year == 2026


def test_updated_at_returns_none_when_minio_down() -> None:
    store, mock_s3 = _make_store()
    mock_s3.get_object.side_effect = ConnectionError("down")
    assert store.updated_at("SPXW") is None


# ---------------------------------------------------------------------------
# IntradayStore.fetch_csv
# ---------------------------------------------------------------------------


def test_fetch_csv_returns_dataframe(tmp_path: Path) -> None:
    store, mock_s3 = _make_store()
    csv_path = _write_csv(tmp_path / "snap.csv")
    mock_s3.get_object.return_value = {"Body": _body(csv_path.read_bytes())}
    df = store.fetch_csv("s3://tickrake/intraday/schwab/snap.csv")
    assert not df.empty
    assert "strike" in df.columns
    mock_s3.get_object.assert_called_once_with(
        Bucket="tickrake", Key="intraday/schwab/snap.csv"
    )


# ---------------------------------------------------------------------------
# IntradayStore.list_roots
# ---------------------------------------------------------------------------


def test_list_roots_returns_json_stems() -> None:
    store, mock_s3 = _make_store()
    paginator_mock = MagicMock()
    mock_s3.get_paginator.return_value = paginator_mock
    paginator_mock.paginate.return_value = [
        {
            "Contents": [
                {"Key": "intraday/schwab/SPXW.json"},
                {"Key": "intraday/schwab/SPX.json"},
                {"Key": "intraday/schwab/candles/SPY.csv"},  # should be ignored (no .json)
            ]
        }
    ]
    result = store.list_roots()
    assert result == ["SPX", "SPXW"]


def test_list_roots_returns_empty_on_error() -> None:
    store, mock_s3 = _make_store()
    mock_s3.get_paginator.side_effect = ConnectionError("down")
    assert store.list_roots() == []


# ---------------------------------------------------------------------------
# Cached module-level functions
# ---------------------------------------------------------------------------


def test_cached_list_expirations(tmp_path: Path) -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-18"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = list_expirations("SPXW", _store=store)
    assert date(2026, 4, 18) in result


def test_cached_find_intraday_updated_at(tmp_path: Path) -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", [])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    ts = find_intraday_updated_at("SPXW", _store=store)
    assert isinstance(ts, datetime)


def test_cached_find_latest_snapshots_respects_0dte_flag() -> None:
    store, mock_s3 = _make_store()
    index = _make_index("SPXW", ["2026-04-15", "2026-04-16"])
    mock_s3.get_object.return_value = {"Body": _body(json.dumps(index))}
    result = find_latest_snapshots(
        "SPXW", start_date=date(2026, 4, 15), days_out=2, include_0dte=False, _store=store
    )
    assert date(2026, 4, 15) not in result
    assert date(2026, 4, 16) in result


def test_cached_load_options_snapshot_s3(tmp_path: Path) -> None:
    store, mock_s3 = _make_store()
    csv_path = _write_csv(tmp_path / "snap.csv")
    mock_s3.get_object.return_value = {"Body": _body(csv_path.read_bytes())}
    df = load_options_snapshot(
        "s3://tickrake/intraday/schwab/snap.csv", _store=store
    )
    assert not df.empty
