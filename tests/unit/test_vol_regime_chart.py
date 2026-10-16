"""Vol regime chart metadata shown for each selected chain."""

from datetime import date

import pandas as pd

from options_monitor.charts.vol_regime import build_vol_regime_chart


def test_hover_shows_selected_expiration_and_actual_dte() -> None:
    data = pd.DataFrame(
        [
            {
                "symbol": "SPXW",
                "iv_rank": 90.0,
                "rr_rank": 0.0,
                "current_iv": 13.2,
                "current_rr": -4.4,
                "sample_date": date(2026, 10, 16),
                "expiration_date": date(2026, 11, 16),
                "actual_dte": 31,
            }
        ]
    )

    trace = build_vol_regime_chart(data).data[0]

    assert "ATM IV percentile" in trace.hovertemplate
    assert "25Δ RR percentile" in trace.hovertemplate
    assert "Expiration: %{customdata[3]}" in trace.hovertemplate
    assert trace.customdata[0][3] == "2026-11-16"
    assert trace.customdata[0][4] == 31


def test_quadrant_labels_show_trade_ideas_on_hover() -> None:
    fig = build_vol_regime_chart(pd.DataFrame(columns=["symbol", "iv_rank", "rr_rank"]))
    tips = [annotation.hovertext for annotation in fig.layout.annotations if annotation.hovertext]

    assert len(tips) == 4
    assert any("buying calls" in tip for tip in tips)
    assert any("buying puts" in tip for tip in tips)
    assert any("selling a call spread" in tip for tip in tips)
    assert any("selling a put spread" in tip for tip in tips)
