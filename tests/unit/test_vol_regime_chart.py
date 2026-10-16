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

    assert "Expiration: %{customdata[3]}" in trace.hovertemplate
    assert trace.customdata[0][3] == "2026-11-16"
    assert trace.customdata[0][4] == 31
