"""Streamlit application for Options Monitor."""

from __future__ import annotations

import streamlit as st
from tractatus.tickrake import TickrakeClient

from options_monitor.config import CANDLE_DIR, OPTIONS_DIR
from options_monitor.tabs.flow import render_flow_tab
from options_monitor.tabs.gex import render_gex_tab
from options_monitor.tabs.history import render_history_tab
from options_monitor.tabs.oi import render_oi_tab
from options_monitor.tabs.vol import render_vol_tab

_TOP_LEVEL_TABS = ["Vol", "GEX", "Flow", "OI", "History"]
_DEFAULT_SYMBOL = "SPXW"


@st.cache_data(ttl=3600)
def _available_roots() -> list[str]:
    """Return sorted option roots from the local tickrake index."""
    client = TickrakeClient()
    roots = client.options_filesystem.list_roots()
    return roots if roots else [_DEFAULT_SYMBOL]


_TAB_SPINNER_MSG: dict[str, str] = {
    "Vol": "Loading Vol...",
    "GEX": "Loading GEX...",
    "History": "Loading History...",
    "Flow": "Loading Flow...",
    "OI": "Loading Open Interest...",
}


def _render_active_dashboard_tab(active_tab: str) -> None:
    """Render only the selected top-level dashboard panel."""
    if active_tab == "Vol":
        render_vol_tab(candle_dir=CANDLE_DIR)
        return
    if active_tab == "GEX":
        render_gex_tab(options_dir=OPTIONS_DIR, candle_dir=CANDLE_DIR)
        return
    if active_tab == "History":
        render_history_tab(options_dir=OPTIONS_DIR, candle_dir=CANDLE_DIR)
        return
    if active_tab == "Flow":
        render_flow_tab(options_dir=OPTIONS_DIR)
        return
    if active_tab == "OI":
        render_oi_tab(options_dir=OPTIONS_DIR)
        return
    raise ValueError(f"Unknown dashboard tab: {active_tab}")


def render_dashboard() -> None:
    """Render the main Options Monitor dashboard."""
    st.set_page_config(
        page_title="Options Monitor",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
    )

    with st.sidebar:
        st.title("Options Monitor")
        roots = _available_roots()
        default_idx = roots.index(_DEFAULT_SYMBOL) if _DEFAULT_SYMBOL in roots else 0
        st.selectbox("Symbol", roots, index=default_idx, key="global_symbol")
        active_tab = str(
            st.radio(
                "Navigation",
                options=_TOP_LEVEL_TABS,
                index=0,
                key="dashboard_tab",
                label_visibility="collapsed",
            )
        )
    with st.spinner(_TAB_SPINNER_MSG.get(active_tab, "Loading...")):
        _render_active_dashboard_tab(active_tab)


if __name__ == "__main__":
    render_dashboard()
