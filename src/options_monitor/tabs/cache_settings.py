"""Dashboard page for persistent chart cache and warmup settings."""

import streamlit as st

from options_monitor.data.cache_settings_ui import render_cache_settings
from options_monitor.data.roots import available_roots


def render_cache_settings_page() -> None:
    st.subheader("Cache Settings")
    st.caption("Settings are saved across sessions and apply to all dashboard users.")
    roots, loaded = available_roots()
    if not loaded:
        st.caption("Loading available symbols… Saved warmup symbols are still available.")
    st.markdown("### Vol Regime")
    render_cache_settings(roots)
