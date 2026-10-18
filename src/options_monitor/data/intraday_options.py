"""Cached dashboard helpers for intraday options indexes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, cast

import streamlit as st
from tractatus.reader import DataReader

from options_monitor.data.reader import get_reader


@st.cache_data(ttl=300)
def list_expirations(symbol: str, _reader: DataReader | None = None) -> list[date]:
    return cast(list[date], (_reader or get_reader()).list_intraday_expirations(symbol))


@st.cache_data(ttl=30)
def find_intraday_updated_at(symbol: str, _reader: DataReader | None = None) -> datetime | None:
    return cast(datetime | None, (_reader or get_reader()).intraday_updated_at(symbol))


@st.cache_data(ttl=30)
def find_series_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: DataReader | None = None,
) -> list[dict[str, Any]]:
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    return (_reader or get_reader()).series_snapshots(symbol, start, end) if start <= end else []


@st.cache_data(ttl=30)
def find_latest_snapshots(
    symbol: str,
    start_date: date,
    days_out: int,
    include_0dte: bool = True,
    _reader: DataReader | None = None,
) -> dict[date, str]:
    start = start_date if include_0dte else start_date + timedelta(days=1)
    end = start_date + timedelta(days=days_out)
    return (_reader or get_reader()).latest_snapshots(symbol, start, end) if start <= end else {}
