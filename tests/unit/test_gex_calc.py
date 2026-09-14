"""Tests for GEX calculation functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_monitor.calc.gex import (
    find_aggregate_wall_strikes,
    find_decision_zones,
    find_top_aggregate_gamma_strikes,
    find_zero_gamma_level,
    net_gex_by_price,
    net_gex_by_strike,
)


def test_net_gex_by_strike_columns(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    result = net_gex_by_strike(spxw_opts, spot=spot)
    assert "strike" in result.columns
    assert "net_gex" in result.columns
    assert len(result) > 0


def test_net_gex_by_strike_has_nonzero_values(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    result = net_gex_by_strike(spxw_opts, spot=spot)
    assert result["net_gex"].max() > 0
    assert result["net_gex"].abs().sum() > 0


def test_find_zero_gamma_level_finds_crossing() -> None:
    prices = np.array([5000.0, 5100.0, 5200.0, 5300.0])
    gex = np.array([-100.0, -50.0, 50.0, 100.0])
    zgl = find_zero_gamma_level(prices, gex)
    assert zgl is not None
    assert 5100.0 < zgl < 5200.0


def test_find_zero_gamma_level_returns_none_when_no_crossing() -> None:
    prices = np.array([5000.0, 5100.0, 5200.0])
    gex = np.array([10.0, 20.0, 30.0])
    assert find_zero_gamma_level(prices, gex) is None


def test_net_gex_by_price_returns_price_gex_columns(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    result = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    assert "price" in result.columns
    assert "net_gex" in result.columns
    assert len(result) > 0


def test_net_gex_by_price_grid_is_integer_spaced(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    result = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap, price_range=10.0)
    diffs = np.diff(result["price"].to_numpy())
    assert np.allclose(diffs, 1.0), "Price grid should be integer-spaced (step=1)"


def test_net_gex_by_price_deterministic_with_snap_time(spxw_opts: pd.DataFrame) -> None:
    spot = float(spxw_opts["underlying_price"].iloc[0])
    snap = pd.Timestamp("2026-04-14 14:00:00")
    r1 = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    r2 = net_gex_by_price(spxw_opts, spot=spot, snap_time=snap)
    pd.testing.assert_frame_equal(r1, r2)


def test_find_aggregate_wall_strikes_returns_side_specific_extrema() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "PUT", "PUT"],
            "strike": [95.0, 105.0, 90.0, 110.0],
            "open_interest": [10.0, 20.0, 15.0, 5.0],
            "gamma": [1.0, 2.0, 3.0, 1.0],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(opts, spot=100.0, strike_range=20.0)

    assert call_wall == 105.0
    assert put_wall == 90.0


def test_find_aggregate_wall_strikes_returns_none_for_missing_side() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL"],
            "strike": [95.0, 105.0],
            "open_interest": [10.0, 20.0],
            "gamma": [1.0, 2.0],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(opts, spot=100.0, strike_range=20.0)

    assert call_wall == 105.0
    assert put_wall is None


def test_find_aggregate_wall_strikes_excludes_strikes_outside_range() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "PUT", "PUT"],
            "strike": [100.0, 140.0, 100.0, 60.0],
            "open_interest": [10.0, 100.0, 8.0, 100.0],
            "gamma": [1.0, 10.0, 1.0, 10.0],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(opts, spot=100.0, strike_range=10.0)

    assert call_wall == 100.0
    assert put_wall == 100.0


def test_find_aggregate_wall_strikes_prefers_call_above_and_put_below_spot() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "PUT", "PUT"],
            "strike": [95.0, 105.0, 110.0, 90.0],
            "open_interest": [50.0, 20.0, 60.0, 15.0],
            "gamma": [4.0, 2.0, 3.0, 2.0],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(opts, spot=100.0, strike_range=20.0)

    assert call_wall == 105.0
    assert put_wall == 90.0


def test_find_top_aggregate_gamma_strikes_returns_side_specific_rankings() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "CALL", "PUT", "PUT", "PUT"],
            "strike": [95.0, 105.0, 110.0, 90.0, 100.0, 115.0],
            "open_interest": [10.0, 25.0, 20.0, 30.0, 15.0, 5.0],
            "gamma": [1.0, 2.0, 1.5, 2.0, 1.0, 0.5],
        }
    )

    top_calls, top_puts = find_top_aggregate_gamma_strikes(
        opts,
        spot=100.0,
        strike_range=20.0,
        top_n=2,
    )

    assert top_calls == [105.0, 110.0]
    assert top_puts == [90.0, 100.0]


def test_find_aggregate_wall_strikes_distance_weighted_prefers_nearer_expiry() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "PUT", "PUT"],
            "strike": [105.0, 110.0, 95.0, 90.0],
            "open_interest": [20.0, 100.0, 20.0, 100.0],
            "gamma": [5.0, 2.0, 5.0, 2.0],
            "expiration_date": ["2026-01-02", "2026-01-11", "2026-01-02", "2026-01-11"],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(
        opts,
        spot=100.0,
        strike_range=20.0,
        method="distance_weighted_aggregate",
        anchor_date=pd.Timestamp("2026-01-01"),
    )

    assert call_wall == 105.0
    assert put_wall == 95.0


def test_find_aggregate_wall_strikes_per_expiry_clustering_prefers_repeated_walls() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": [
                "CALL",
                "CALL",
                "CALL",
                "CALL",
                "CALL",
                "CALL",
                "PUT",
                "PUT",
                "PUT",
                "PUT",
                "PUT",
                "PUT",
            ],
            "strike": [
                105.0,
                110.0,
                105.0,
                115.0,
                110.0,
                115.0,
                95.0,
                90.0,
                95.0,
                85.0,
                90.0,
                85.0,
            ],
            "open_interest": [10.0, 30.0, 12.0, 8.0, 14.0, 40.0, 10.0, 30.0, 12.0, 8.0, 14.0, 40.0],
            "gamma": [2.0, 1.0, 2.0, 1.0, 2.0, 0.5, 2.0, 1.0, 2.0, 1.0, 2.0, 0.5],
            "expiration_date": [
                "2026-01-02",
                "2026-01-02",
                "2026-01-03",
                "2026-01-03",
                "2026-01-04",
                "2026-01-04",
                "2026-01-02",
                "2026-01-02",
                "2026-01-03",
                "2026-01-03",
                "2026-01-04",
                "2026-01-04",
            ],
        }
    )

    call_wall, put_wall = find_aggregate_wall_strikes(
        opts,
        spot=100.0,
        strike_range=20.0,
        method="per_expiry_clustering",
    )

    assert call_wall == 110.0
    assert put_wall == 90.0


def test_find_top_aggregate_gamma_strikes_supports_per_expiry_clustering() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "CALL", "PUT", "PUT", "PUT"],
            "strike": [105.0, 110.0, 105.0, 95.0, 90.0, 95.0],
            "open_interest": [20.0, 25.0, 15.0, 20.0, 25.0, 15.0],
            "gamma": [2.0, 1.0, 2.0, 2.0, 1.0, 2.0],
            "expiration_date": [
                "2026-01-02",
                "2026-01-02",
                "2026-01-03",
                "2026-01-02",
                "2026-01-02",
                "2026-01-03",
            ],
        }
    )

    top_calls, top_puts = find_top_aggregate_gamma_strikes(
        opts,
        spot=100.0,
        strike_range=20.0,
        top_n=2,
        method="per_expiry_clustering",
    )

    assert top_calls == [105.0]
    assert top_puts == [95.0]


def test_find_decision_zones_distance_weighted_returns_otm_bands() -> None:
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL", "CALL", "CALL", "PUT", "PUT", "PUT"],
            "strike": [105.0, 110.0, 130.0, 95.0, 90.0, 70.0],
            "open_interest": [30.0, 15.0, 40.0, 25.0, 15.0, 40.0],
            "gamma": [2.0, 2.0, 1.0, 2.0, 2.0, 1.0],
            "expiration_date": [
                "2026-01-02",
                "2026-01-02",
                "2026-01-15",
                "2026-01-02",
                "2026-01-02",
                "2026-01-15",
            ],
        }
    )

    resistance_zones, support_zones = find_decision_zones(
        opts,
        spot=100.0,
        strike_range=35.0,
        anchor_date=pd.Timestamp("2026-01-01"),
        top_n=1,
        merge_gap=10.0,
        zone_pad=5.0,
    )

    assert len(resistance_zones) == 1
    assert len(support_zones) == 1
    assert resistance_zones[0]["low"] == 100.0
    assert resistance_zones[0]["high"] == 110.0
    assert support_zones[0]["low"] == 90.0
    assert support_zones[0]["high"] == 100.0


def test_find_decision_zones_limits_zone_width_for_dense_side() -> None:
    strikes = [100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0]
    opts = pd.DataFrame(
        {
            "contract_type": ["CALL"] * len(strikes) + ["PUT"] * len(strikes),
            "strike": strikes + [100.0 - (s - 100.0) for s in strikes],
            "open_interest": [50.0, 80.0, 120.0, 140.0, 120.0, 80.0, 50.0] * 2,
            "gamma": [1.0] * (len(strikes) * 2),
            "expiration_date": ["2026-01-02"] * (len(strikes) * 2),
        }
    )

    resistance_zones, support_zones = find_decision_zones(
        opts,
        spot=100.0,
        strike_range=35.0,
        anchor_date=pd.Timestamp("2026-01-01"),
        top_n=1,
        merge_gap=10.0,
        zone_pad=5.0,
    )

    assert len(resistance_zones) == 1
    assert len(support_zones) == 1
    assert resistance_zones[0]["high"] - resistance_zones[0]["low"] <= 20.0
    assert support_zones[0]["high"] - support_zones[0]["low"] <= 20.0
