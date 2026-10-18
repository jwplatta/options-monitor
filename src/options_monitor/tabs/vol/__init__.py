"""Vol tab package."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from options_monitor.config import OPTIONS_DIR
from options_monitor.tabs.vol.fixed_strike import render_fixed_strike_tab
from options_monitor.tabs.vol.overview import render_overview_tab
from options_monitor.tabs.vol.spx_rv import render_spx_rv_tab
from options_monitor.tabs.vol.vol_regime import render_vol_regime_tab


def render_vol_tab(candle_dir: Path, options_dir: Path = OPTIONS_DIR) -> None:
    st.subheader("Volatility")

    tab_overview, tab_spx_rv, tab_fsv, tab_regime = st.tabs(
        ["Overview", "SPX RV", "Fixed Strike Vol", "Vol Regime"]
    )

    with tab_overview:
        _safe_render(render_overview_tab, candle_dir)

    with tab_spx_rv:
        _safe_render(render_spx_rv_tab, candle_dir)

    with tab_fsv:
        _safe_render(render_fixed_strike_tab, options_dir)

    with tab_regime:
        _safe_render(render_vol_regime_tab, options_dir)


def _safe_render(render_fn: object, *args: object) -> None:
    """Render a sub-tab, catching errors so one broken tab doesn't crash the rest."""
    try:
        render_fn(*args)  # type: ignore[operator]
    except Exception as exc:
        st.error(f"Error loading tab: {exc}")
