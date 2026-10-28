"""Independent symbol controls for dashboard charts."""

from __future__ import annotations

import streamlit as st

from options_monitor.data.roots import available_roots


def symbol_selector(chart_id: str) -> str:
    """Render a chart-owned selector without changing another chart's state."""
    key = f"{chart_id}_symbol"
    roots, loaded = available_roots()
    current = str(st.session_state.get(key, "SPXW"))
    options = list(dict.fromkeys([current, *roots]))
    selected = str(st.selectbox("Symbol", options, index=options.index(current), key=key))
    if not loaded:
        st.caption("Loading symbols…")
    return selected
