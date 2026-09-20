"""History tab: historical GEX and chain replay views."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from options_monitor.tabs.gex import (
    _render_gex_history_view,
    _render_history_view,
    _select_single_expiry,
)

_HISTORY_VIEWS = ["GEX History", "Chain GEX History"]
_SINGLE_EXPIRY_VIEWS = {"Chain GEX History"}


def _render_active_history_view(
    active_view: str,
    symbol: str,
    include_0dte: bool,
    range_pct: float,
    selected_exp_str: str | None,
    options_dir: Path,
) -> None:
    if active_view == "GEX History":
        _render_gex_history_view(symbol, include_0dte, range_pct, options_dir)
        return

    if selected_exp_str is None:
        st.warning(f"No expirations available for {symbol}.")
        return

    if active_view == "Chain GEX History":
        _render_history_view(symbol, date.fromisoformat(selected_exp_str), range_pct, options_dir)
        return

    raise ValueError(f"Unknown History view: {active_view}")


def render_history_tab(options_dir: Path, candle_dir: Path) -> None:
    del candle_dir
    st.subheader("History")

    @st.fragment(run_every="5m")
    def _render() -> None:
        col_ctrl, col_chart = st.columns([1, 3])

        with col_ctrl:
            include_0dte = st.toggle("Include 0DTE", value=True, key="gm_0dte")
            symbol = str(st.session_state.get("global_symbol", "SPXW"))
            range_pct = float(
                st.slider(
                    "Strike range (% of spot)",
                    min_value=1,
                    max_value=25,
                    value=5,
                    step=1,
                    key="gm_range_pct",
                )
            )

        today = date.today()

        with col_chart:
            active_view = str(
                st.segmented_control(
                    "History View",
                    options=_HISTORY_VIEWS,
                    default="GEX History",
                    selection_mode="single",
                    key="history_view",
                    label_visibility="collapsed",
                )
            )

        selected_exp_str: str | None = None
        if active_view in _SINGLE_EXPIRY_VIEWS:
            with col_ctrl:
                st.divider()
                selected_exp_str = _select_single_expiry(symbol, today, options_dir)

        with col_chart:
            _render_active_history_view(
                active_view=active_view,
                symbol=symbol,
                include_0dte=include_0dte,
                range_pct=range_pct,
                selected_exp_str=selected_exp_str,
                options_dir=options_dir,
            )

    _render()
