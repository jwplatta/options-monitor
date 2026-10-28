"""Cached dashboard helpers for intraday options indexes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import streamlit as st
from tractatus.reader import Reader

from options_monitor.data.reader import get_reader

_CHICAGO = ZoneInfo("America/Chicago")


@st.cache_data(ttl=60)
def list_expirations(symbol: str, _reader: Reader | None = None) -> list[date]:
    return cast(list[date], (_reader or get_reader()).list_intraday_expirations(symbol))


@st.cache_data(ttl=30)
def find_intraday_updated_at(symbol: str, _reader: Reader | None = None) -> datetime | None:
    return cast(datetime | None, (_reader or get_reader()).intraday_updated_at(symbol))


@st.cache_data(ttl=30)
def find_series_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: Reader | None = None,
) -> list[dict[str, Any]]:
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    return (_reader or get_reader()).series_snapshots(symbol, start, end) if start <= end else []


@st.cache_data(ttl=30)
def find_first_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: Reader | None = None,
) -> dict[date, dict[str, Any]]:
    """Return the earliest intraday snapshot entry for each expiration date."""
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    if start > end:
        return {}

    entries = (_reader or get_reader()).series_snapshots(symbol, start, end)
    first_by_expiry: dict[date, tuple[datetime, dict[str, Any]]] = {}
    for entry in entries:
        expiry = date.fromisoformat(str(entry["expiration_date"]))
        sampled_at = datetime.fromisoformat(str(entry["sampled_at"]).replace("Z", "+00:00"))
        if sampled_at.tzinfo is None:
            sampled_at = sampled_at.replace(tzinfo=UTC)
        if sampled_at.astimezone(_CHICAGO).date() != start_date:
            continue
        current = first_by_expiry.get(expiry)
        if current is None or sampled_at < current[0]:
            first_by_expiry[expiry] = (sampled_at, entry)
    return {expiry: entry for expiry, (_, entry) in sorted(first_by_expiry.items())}


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: Reader | None = None,
) -> dict[date, str]:
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    return (_reader or get_reader()).latest_snapshots(symbol, start, end) if start <= end else {}
