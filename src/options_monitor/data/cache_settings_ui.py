"""Persistent warmup and retention controls shared by registered chart jobs."""

import streamlit as st

from options_monitor.data.vol_regime_jobs import runtime


def render_cache_settings(roots: list[str]) -> None:
    jobs = runtime()
    with st.expander("Historical cache settings"):
        current = jobs.targets("vol_regime")
        if not jobs.setting("vol_regime:watchlist_initialized", False):
            current = ["SPXW"]
        current_dte = jobs.setting("vol_regime:warmup_params", {"target_dte": 30})["target_dte"]
        with st.form("vol_regime_cache_settings"):
            targets = st.multiselect(
                "Warmup symbols", sorted(set(roots + current)), default=current
            )
            dte = st.selectbox(
                "Warmup target DTE", [5, 15, 30, 45], index=[5, 15, 30, 45].index(current_dte)
            )
            retention = st.number_input(
                "Historical retention (calendar days)",
                min_value=1,
                max_value=36500,
                value=jobs.retention("vol_regime"),
                step=1,
            )
            if st.form_submit_button("Save cache settings"):
                jobs.set_targets("vol_regime", list(targets), {"target_dte": int(dte)})
                jobs.set_setting("vol_regime:retention_days", int(retention))
                jobs.set_setting("vol_regime:cleanup_date", "")
                with jobs.connection() as db:
                    db.execute(
                        "UPDATE cache_job_state SET completed_at=NULL "
                        "WHERE namespace_id=? AND job_id='vol_regime' AND status='ready'",
                        (jobs.namespace,),
                    )
                st.success("Cache settings saved.")
