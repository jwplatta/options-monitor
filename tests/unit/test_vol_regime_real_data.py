"""Regression calculations against frozen SPXW market chains, with fixed oracles."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from options_monitor.calc.risk_reversal import compute_risk_reversal
from options_monitor.calc.vol_regime import build_vol_regime_row, compute_atm_iv
from options_monitor.data.vol_regime_cache import VolRegimeObservationStore

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "vol_regime"
_EXPECTED = json.loads((_FIXTURE / "expected.json").read_text())


def _chains() -> pd.DataFrame:
    return pd.read_csv(_FIXTURE / "spxw_chains.csv", parse_dates=["sampled_at"])


@pytest.mark.parametrize("expected", _EXPECTED, ids=[row["sampled_at"] for row in _EXPECTED])
def test_real_chain_atm_and_interpolated_25_delta_ivs(expected):
    chains = _chains()
    chain = chains[chains.sampled_at.eq(pd.Timestamp(expected["sampled_at"]))]
    assert not chain.empty
    spot = float(chain.underlying_price.iloc[0])
    assert compute_atm_iv(chain, spot) == pytest.approx(expected["atm_iv"], abs=1e-10)
    rr = compute_risk_reversal(chain)
    assert rr is not None
    assert rr.iv_25d_call == pytest.approx(expected["iv_25d_call"], abs=1e-10)
    assert rr.iv_25d_put == pytest.approx(expected["iv_25d_put"], abs=1e-10)
    assert rr.rr == pytest.approx(expected["risk_reversal"], abs=1e-10)


def test_real_observations_cached_then_ranked_without_current_day_leakage(tmp_path):
    chains = _chains()
    path = tmp_path / "real_metrics.sqlite3"
    with VolRegimeObservationStore(path) as store:
        for day, daily in chains.groupby("sample_date", sort=True):
            observations = []
            for timestamp, chain in daily.groupby("sampled_at", sort=True):
                rr = compute_risk_reversal(chain)
                assert rr is not None
                observations.append(
                    (
                        str(timestamp),
                        compute_atm_iv(chain, float(chain.underlying_price.iloc[0])),
                        rr.rr,
                    )
                )
            store.put(
                "SPXW",
                date.fromisoformat(str(day)),
                30,
                "captured-real-source",
                observations,
                str(daily.expiration_date.iloc[0]),
            )
    # Reopen to exercise persistence. October 15's two observations must be excluded.
    with VolRegimeObservationStore(path) as store:
        ivs, rrs, through = store.get_range("SPXW", 30, date(2026, 10, 12), date(2026, 10, 15))
    assert len(ivs) == len(rrs) == 6
    assert through == date(2026, 10, 14)
    current = chains[chains.sampled_at.eq(chains.sampled_at.max())]
    rr = compute_risk_reversal(current)
    assert rr is not None
    iv = compute_atm_iv(current, float(current.underlying_price.iloc[0]))
    assert iv is not None
    point = build_vol_regime_row(iv, rr.rr, ivs, rrs)
    assert point is not None
    assert point.current_iv == pytest.approx(11.405)
    assert point.current_rr == pytest.approx(-2.6157142857142857)
    # Five historical ATM IVs are <= 11.405; only one historical RR is <= -2.615714...
    assert point.iv_rank == pytest.approx(100 * 5 / 6)
    assert point.rr_rank == pytest.approx(100 * 1 / 6)
