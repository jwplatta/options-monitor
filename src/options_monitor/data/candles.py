"""Cached candle loader backed by the Tractatus reader."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st
from tractatus.reader import Reader

from options_monitor.data.reader import get_reader

_PROVIDER = "ibkr-paper"


@st.cache_data(ttl=300)
def _load_full_candles(symbol: str, freq: str, _reader: Reader | None = None) -> pd.DataFrame:
    df = (_reader or get_reader()).candles(_PROVIDER, symbols=[symbol], frequency=freq)
    return df[["datetime", "open", "high", "low", "close", "volume"]]  # type: ignore[no-any-return]


def load_candles(
    symbol: str,
    freq: str,
    start: date | None = None,
    end: date | None = None,
    _reader: Reader | None = None,
) -> pd.DataFrame:
    df = _load_full_candles(symbol, freq, _reader)
    tz = df["datetime"].dt.tz
    if start is not None:
        start_ts = pd.Timestamp(start, tz="UTC") if tz is not None else pd.Timestamp(start)
        df = df[df["datetime"] >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end, tz="UTC") if tz is not None else pd.Timestamp(end)
        df = df[df["datetime"] <= end_ts]
    return df.reset_index(drop=True)


@st.cache_data(ttl=300)
def list_available_dates(
    symbol: str, freq: str, _reader: Reader | None = None
) -> tuple[datetime, datetime]:
    df = _load_full_candles(symbol, freq, _reader)
    return df["datetime"].iloc[0].to_pydatetime(), df["datetime"].iloc[-1].to_pydatetime()
