"""Dashboard page for persistent chart cache and warmup settings."""

import streamlit as st

from options_monitor.data.cache_settings_ui import render_cache_settings
from options_monitor.data.roots import available_root_details, available_roots
from options_monitor.data.vol_regime_jobs import runtime


def render_settings_page() -> None:
    st.subheader("Settings")
    st.caption("Settings are saved across sessions and apply to all dashboard users.")
    jobs = runtime()
    st.markdown("### Option roots")
    st.caption(
        "Supported roots and underlying symbols are configured in "
        "src/options_monitor/config/option_roots.yaml. Edit that file and restart "
        "the app to update the registry."
    )
    details = available_root_details()
    st.caption(f"{len(details)} configured option roots")
    st.dataframe(details, hide_index=True, width="stretch", height=360)
    roots, _ = available_roots()
    st.markdown("### Shared warmup list")
    st.caption(
        "These symbols are warmed for every chart with a registered cache job. "
        "Leave the list empty to cache only when charts are requested."
    )
    current = jobs.targets("vol_regime")
    with st.form("shared_cache_warmup"):
        targets = st.multiselect("Warmup symbols", sorted(set(roots + current)), default=current)
        if st.form_submit_button("Save warmup list"):
            jobs.set_shared_targets(list(targets))
            st.success("Shared warmup list saved.")
    st.markdown("### Vol Regime")
    render_cache_settings()
