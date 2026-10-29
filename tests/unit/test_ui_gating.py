from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from options_monitor import app
from options_monitor.tabs import gex as gamma_map
from options_monitor.tabs import history


def test_chart_symbol_selectors_are_independent(monkeypatch) -> None:
    from options_monitor.data import symbol_selector as selectors

    state = {"gex_symbol": "SPY", "history_symbol": "QQQ"}
    monkeypatch.setattr(selectors.st, "session_state", state)
    monkeypatch.setattr(selectors, "available_roots", lambda: (["SPXW", "SPY"], True))
    monkeypatch.setattr(
        selectors.st, "selectbox", lambda label, options, index, key: options[index]
    )
    assert selectors.symbol_selector("gex") == "SPY"
    assert selectors.symbol_selector("history") == "QQQ"
    assert "global_symbol" not in state


def test_dashboard_router_only_invokes_selected_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(app, "render_vol_tab", lambda: calls.append("vol"))
    monkeypatch.setattr(
        app,
        "render_gex_tab",
        lambda: calls.append("gex"),
    )
    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda: calls.append("history"),
    )
    monkeypatch.setattr(app, "render_flow_tab", lambda: calls.append("flow"))
    monkeypatch.setattr(app, "render_oi_tab", lambda: calls.append("oi"))

    app._render_active_dashboard_tab("Vol")
    assert calls == ["vol"]


def test_dashboard_router_dispatches_history_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda: calls.append("history"),
    )

    app._render_active_dashboard_tab("History")
    assert calls == ["history"]


def test_gamma_router_only_invokes_selected_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        gamma_map,
        "_render_gex_view",
        lambda symbol, today, include_0dte, range_pct: calls.append("gex"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_chains_view",
        lambda symbol, selected_exp, range_pct: calls.append("chains"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_gamma_heatmap_view",
        lambda symbol, today, include_0dte, range_pct: calls.append("heatmap"),
    )

    gamma_map._render_active_gex_view(
        active_view="GEX",
        symbol="SPXW",
        today=date(2026, 4, 15),
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str="2026-04-18",
    )
    assert calls == ["gex"]


def test_gamma_router_rejects_unknown_view(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Unknown GEX view"):
        gamma_map._render_active_gex_view(
            active_view="Nonexistent View",
            symbol="SPXW",
            today=date(2026, 4, 15),
            include_0dte=True,
            range_pct=5.0,
            selected_exp_str="2026-04-18",
        )


def test_history_router_dispatches_chain_history_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(history, "_render_history_view", lambda *args: calls.append("history"))

    history._render_active_history_view(
        active_view="Chain GEX History",
        symbol="SPXW",
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str="2026-04-18",
    )
    assert calls == ["history"]


def test_history_router_dispatches_aggregate_history_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        history,
        "_render_gex_history_view",
        lambda *args: calls.append("gex_history"),
    )

    history._render_active_history_view(
        active_view="GEX History",
        symbol="SPXW",
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str=None,
    )
    assert calls == ["gex_history"]


def test_render_history_tab_only_requests_single_expiry_for_chain_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selectbox_calls: list[str] = []

    monkeypatch.setattr(history.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(history.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(history.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(history.st, "toggle", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(history.st, "divider", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        history.st,
        "segmented_control",
        lambda *args, **kwargs: "Chain GEX History",
    )

    def _selectbox(label, options, index=0, key=None):
        selectbox_calls.append(label)
        return options[index]

    monkeypatch.setattr(history.st, "selectbox", _selectbox)
    monkeypatch.setattr(
        history,
        "_select_single_expiry",
        lambda symbol, today: "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab()

    assert selectbox_calls == ["Symbol"]


def test_render_history_tab_skips_single_expiry_for_aggregate_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_exp_calls: list[str] = []

    monkeypatch.setattr(history.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(history.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(history.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(history.st, "toggle", lambda *args, **kwargs: True)
    monkeypatch.setattr(history.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(history.st, "segmented_control", lambda *args, **kwargs: "GEX History")
    monkeypatch.setattr(
        history.st, "selectbox", lambda label, options, index=0, key=None: options[index]
    )
    monkeypatch.setattr(
        history,
        "_select_single_expiry",
        lambda symbol, today: selected_exp_calls.append(symbol) or "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab()

    assert selected_exp_calls == []


def test_gex_view_does_not_touch_history_snapshot_loader(monkeypatch, tmp_path: Path) -> None:
    sample_df = pd.DataFrame(
        [
            {
                "underlying_price": 5000.0,
                "strike": 5000.0,
                "gamma": 0.01,
                "volatility": 20.0,
                "open_interest": 100.0,
                "contract_type": "CALL",
            }
        ]
    )
    history_loader_called: list[str] = []

    from datetime import datetime

    monkeypatch.setattr(
        gamma_map,
        "_load_window_snapshot_data",
        lambda **kwargs: (
            sample_df,
            5000.0,
            250,
            datetime(2026, 4, 15, 15, 0, 0),
            False,
        ),
    )
    monkeypatch.setattr(
        gamma_map,
        "find_historical_snapshot_times",
        lambda *args, **kwargs: history_loader_called.append("find_historical") or [],
    )
    monkeypatch.setattr(
        gamma_map,
        "load_historical_snapshot",
        lambda *args, **kwargs: history_loader_called.append("load_historical") or sample_df,
    )
    monkeypatch.setattr(gamma_map, "net_gex_by_strike", lambda df, spot, strike_range: sample_df)
    monkeypatch.setattr(gamma_map, "net_gex_by_price", lambda df, spot, price_range: sample_df)
    monkeypatch.setattr(gamma_map, "find_raw_wall_strikes", lambda *a, **kw: (None, None))
    monkeypatch.setattr(gamma_map, "find_aggregate_wall_strikes", lambda *a, **kw: (None, None))
    monkeypatch.setattr(gamma_map, "find_decision_zones", lambda *a, **kw: ([], []))
    monkeypatch.setattr(gamma_map, "build_gex_aggregate_chart", lambda *args, **kwargs: object())
    monkeypatch.setattr(gamma_map.st, "radio", lambda *args, **kwargs: 5)
    monkeypatch.setattr(gamma_map.st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(gamma_map.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "warning", lambda *args, **kwargs: None)

    gamma_map._render_gex_view(
        symbol="SPXW",
        today=date(2026, 4, 15),
        include_0dte=True,
        range_pct=5.0,
    )

    assert history_loader_called == []


def test_gex_filter_excludes_invalid_greeks_and_reports_partial_sample(monkeypatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(gamma_map.st, "warning", warnings.append)
    rows = pd.DataFrame(
        [
            {
                "strike": 5000,
                "gamma": 0.01,
                "volatility": 20,
                "open_interest": 100,
                "contract_type": "CALL",
            },
            {
                "strike": 4990,
                "gamma": -999,
                "volatility": 20,
                "open_interest": 100,
                "contract_type": "PUT",
            },
            {
                "strike": 5010,
                "gamma": 0.01,
                "volatility": -999,
                "open_interest": 100,
                "contract_type": "CALL",
            },
        ]
    )

    filtered = gamma_map._usable_gex_rows(rows, "SPXW")

    assert filtered["strike"].tolist() == [5000]
    assert len(warnings) == 1
    assert "1 of 3" in warnings[0]
    assert rows["gamma"].tolist() == [0.01, -999, 0.01]


def test_gex_view_shows_empty_state_instead_of_plotting_invalid_sample(monkeypatch) -> None:
    rows = pd.DataFrame(
        [
            {
                "underlying_price": 7691.0,
                "strike": 7700.0,
                "gamma": -999.0,
                "volatility": -999.0,
                "open_interest": 100.0,
                "contract_type": "CALL",
            }
        ]
    )
    warnings: list[str] = []
    plotted: list[object] = []
    monkeypatch.setattr(
        gamma_map,
        "_load_window_snapshot_data",
        lambda **kwargs: (rows, 7691.0, 385, None, False),
    )
    monkeypatch.setattr(gamma_map.st, "radio", lambda *args, **kwargs: 5)
    monkeypatch.setattr(gamma_map.st, "warning", warnings.append)
    monkeypatch.setattr(gamma_map.st, "plotly_chart", lambda fig, **kwargs: plotted.append(fig))
    monkeypatch.setattr(
        gamma_map,
        "net_gex_by_strike",
        lambda *args, **kwargs: pytest.fail("GEX calculation received invalid contracts"),
    )

    gamma_map._render_gex_view("SPXW", date(2026, 10, 19), True, 5.0)

    assert not plotted
    assert len(warnings) == 1
    assert "No valid SPXW GEX contracts" in warnings[0]


def test_history_view_uses_selected_snapshot_and_reuses_single_expiry_chart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from datetime import datetime

    sample_df = pd.DataFrame(
        [
            {
                "underlying_price": 5000.0,
                "strike": 5000.0,
                "gamma": 0.01,
                "volatility": 20.0,
                "open_interest": 100.0,
                "contract_type": "CALL",
            }
        ]
    )
    parquet_path = tmp_path / "SPXW_samples_2026-04-15.parquet"
    parquet_path.touch()
    snapshot_times = [
        datetime(2026, 4, 15, 14, 0, 0),
        datetime(2026, 4, 15, 15, 0, 0),
    ]
    chart_calls: list[tuple[float, float, str]] = []
    plotted: list[object] = []

    monkeypatch.setattr(
        gamma_map,
        "list_snapshot_dates_for_expiry",
        lambda symbol, expiry: [date(2026, 4, 15)],
    )
    monkeypatch.setattr(
        gamma_map,
        "parquet_path_for_date",
        lambda symbol, sample_date: parquet_path,
    )
    monkeypatch.setattr(
        gamma_map,
        "find_historical_snapshot_times",
        lambda expiry, parquet_path: snapshot_times,
    )
    monkeypatch.setattr(
        gamma_map,
        "load_historical_snapshot",
        lambda symbol, expiry, ts, parquet_path: sample_df,
    )
    monkeypatch.setattr(
        gamma_map,
        "build_gex_single_expiry_chart",
        lambda opts, spot, strike_range, title: (
            chart_calls.append((spot, strike_range, title)) or object()
        ),
    )
    monkeypatch.setattr(gamma_map.st, "date_input", lambda *args, **kwargs: date(2026, 4, 15))
    monkeypatch.setattr(
        gamma_map.st,
        "select_slider",
        lambda *args, **kwargs: kwargs["options"][1],
    )
    monkeypatch.setattr(gamma_map.st, "spinner", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(gamma_map.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "plotly_chart", lambda fig, **kwargs: plotted.append(fig))
    monkeypatch.setattr(gamma_map.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "session_state", {})

    gamma_map._render_history_view(
        symbol="SPXW",
        selected_exp=date(2026, 4, 18),
        range_pct=5.0,
    )

    assert len(chart_calls) == 1
    assert chart_calls[0][0] == 5000.0
    assert "Chain GEX History" in chart_calls[0][2]
    assert plotted


def test_history_view_warns_when_selected_date_has_no_snapshots(
    monkeypatch, tmp_path: Path
) -> None:
    warnings: list[str] = []

    monkeypatch.setattr(
        gamma_map,
        "list_snapshot_dates_for_expiry",
        lambda symbol, expiry: [date(2026, 4, 15)],
    )
    monkeypatch.setattr(gamma_map.st, "date_input", lambda *args, **kwargs: date(2026, 4, 16))
    monkeypatch.setattr(gamma_map.st, "warning", lambda message: warnings.append(message))

    gamma_map._render_history_view(
        symbol="SPXW",
        selected_exp=date(2026, 4, 18),
        range_pct=5.0,
    )

    assert warnings


def test_render_gex_tab_has_own_symbol_selector(monkeypatch, tmp_path: Path) -> None:
    """GEX tab reads symbol from global session state, not its own selectbox."""
    monkeypatch.setattr(gamma_map.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(gamma_map.st, "fragment", lambda **kwargs: lambda func: func)
    monkeypatch.setattr(gamma_map.st, "columns", lambda spec: (nullcontext(), nullcontext()))
    monkeypatch.setattr(gamma_map.st, "toggle", lambda *args, **kwargs: True)
    monkeypatch.setattr(gamma_map.st, "selectbox", lambda *args, **kwargs: "GEX")
    monkeypatch.setattr(gamma_map.st, "slider", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(gamma_map.st, "segmented_control", lambda *args, **kwargs: "GEX")
    monkeypatch.setattr(gamma_map, "_render_active_gex_view", lambda **kwargs: None)

    # No selectbox with "Symbol" label should be called — symbol comes from session state.
    selectbox_labels: list[str] = []
    original_selectbox = gamma_map.st.selectbox

    def _tracking_selectbox(label, *args, **kwargs):
        selectbox_labels.append(label)
        return original_selectbox(label, *args, **kwargs)

    monkeypatch.setattr(gamma_map.st, "selectbox", _tracking_selectbox)

    gamma_map.render_gex_tab()

    assert "Symbol" in selectbox_labels


def test_cache_settings_router_does_not_render_charts(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(app, "render_cache_settings_page", lambda: calls.append("settings"))
    monkeypatch.setattr(app, "render_vol_tab", lambda: calls.append("vol"))
    app._render_active_dashboard_tab("Cache Settings")
    assert calls == ["settings"]
    assert "Cache Settings" in app._TOP_LEVEL_TABS


def test_roots_ready_triggers_full_rerun_to_refresh_dropdowns(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "available_roots", lambda: (["QQQ", "SPY"], True))
    monkeypatch.setattr(app.st, "rerun", lambda **kwargs: calls.append(kwargs))
    app._wait_for_roots.__wrapped__()
    assert calls == [{"scope": "app"}]


def test_pending_roots_do_not_rerun_entire_app(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "available_roots", lambda: (["SPXW"], False))
    monkeypatch.setattr(app.st, "caption", lambda *args: None)
    monkeypatch.setattr(app.st, "rerun", lambda **kwargs: calls.append(kwargs))
    app._wait_for_roots.__wrapped__()
    assert calls == []
