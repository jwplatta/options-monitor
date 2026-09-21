from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from options_monitor import app
from options_monitor.tabs import gex as gamma_map
from options_monitor.tabs import history


def test_dashboard_router_only_invokes_selected_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(app, "render_vol_tab", lambda candle_dir: calls.append("vol"))
    monkeypatch.setattr(
        app,
        "render_gex_tab",
        lambda options_dir, candle_dir: calls.append("gex"),
    )
    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda options_dir, candle_dir: calls.append("history"),
    )
    monkeypatch.setattr(app, "render_flow_tab", lambda options_dir: calls.append("flow"))
    monkeypatch.setattr(app, "render_oi_tab", lambda options_dir: calls.append("oi"))

    app._render_active_dashboard_tab("Vol")
    assert calls == ["vol"]


def test_dashboard_router_dispatches_history_panel(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        app,
        "render_history_tab",
        lambda options_dir, candle_dir: calls.append("history"),
    )

    app._render_active_dashboard_tab("History")
    assert calls == ["history"]


def test_gamma_router_only_invokes_selected_view(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        gamma_map,
        "_render_gex_view",
        lambda symbol, today, include_0dte, range_pct, options_dir: calls.append("gex"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_chains_view",
        lambda symbol, selected_exp, range_pct, options_dir: calls.append("chains"),
    )
    monkeypatch.setattr(
        gamma_map,
        "_render_gamma_heatmap_view",
        lambda symbol, today, include_0dte, range_pct, options_dir: calls.append("heatmap"),
    )

    gamma_map._render_active_gex_view(
        active_view="GEX",
        symbol="SPXW",
        today=date(2026, 4, 15),
        include_0dte=True,
        range_pct=5.0,
        selected_exp_str="2026-04-18",
        options_dir=Path("/tmp/options"),
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
            options_dir=Path("/tmp/options"),
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
        options_dir=Path("/tmp/options"),
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
        options_dir=Path("/tmp/options"),
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
        lambda symbol, today, options_dir: "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab(options_dir=tmp_path, candle_dir=tmp_path)

    # Symbol selector moved to global sidebar; history tab has no selectboxes.
    assert selectbox_calls == []


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
        lambda symbol, today, options_dir: selected_exp_calls.append(symbol) or "2026-04-18",
    )
    monkeypatch.setattr(history, "_render_active_history_view", lambda **kwargs: None)

    history.render_history_tab(options_dir=tmp_path, candle_dir=tmp_path)

    assert selected_exp_calls == []


def test_gex_view_does_not_touch_history_snapshot_loader(monkeypatch, tmp_path: Path) -> None:
    sample_df = pd.DataFrame(
        [{"underlying_price": 5000.0, "strike": 5000.0, "gamma": 0.01, "open_interest": 100.0}]
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
        options_dir=tmp_path,
    )

    assert history_loader_called == []


def test_history_view_uses_selected_snapshot_and_reuses_single_expiry_chart(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from datetime import datetime

    sample_df = pd.DataFrame(
        [{"underlying_price": 5000.0, "strike": 5000.0, "gamma": 0.01, "open_interest": 100.0}]
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
        options_dir=tmp_path,
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
        options_dir=tmp_path,
    )

    assert warnings


def test_render_gex_tab_reads_global_symbol(monkeypatch, tmp_path: Path) -> None:
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

    gamma_map.render_gex_tab(options_dir=tmp_path, candle_dir=tmp_path)

    assert "Symbol" not in selectbox_labels
