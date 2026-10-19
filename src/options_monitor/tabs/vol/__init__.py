"""Vol tab package."""

from __future__ import annotations

import streamlit as st

from options_monitor.tabs.vol.fixed_strike import render_fixed_strike_tab
from options_monitor.tabs.vol.skew_history import render_skew_history_tab
from options_monitor.tabs.vol.vol_regime import render_vol_regime_tab


def render_vol_tab() -> None:
    st.subheader("Volatility")

    tab_fsv, tab_skew, tab_regime = st.tabs(
        ["Fixed Strike Vol", "Volatility Skew", "Vol Regime"],
        default="Vol Regime",
        on_change="rerun",
        key="vol_subtab",
    )

    with tab_fsv:
        if tab_fsv.open:
            _safe_render(render_fixed_strike_tab)

    with tab_skew:
        if tab_skew.open:
            _safe_render(render_skew_history_tab)

    with tab_regime:
        if tab_regime.open:
            _safe_render(render_vol_regime_tab)


def _safe_render(render_fn: object, *args: object) -> None:
    """Render a sub-tab, catching errors so one broken tab doesn't crash the rest."""
    try:
        render_fn(*args)  # type: ignore[operator]
    except Exception as exc:
        st.error(f"Error loading tab: {exc}")
