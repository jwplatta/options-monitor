"""Day-over-day open-interest changes for option chains."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

_CHICAGO = ZoneInfo("America/Chicago")
_CONTRACT_KEYS = ["expiration_date", "strike", "contract_type"]
_OUTPUT_COLUMNS = [*_CONTRACT_KEYS, "open_interest", "underlying_price"]


def _normalize_chain(frame: pd.DataFrame) -> pd.DataFrame:
    required = {*_CONTRACT_KEYS, "open_interest", "underlying_price"}
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    columns = [*_OUTPUT_COLUMNS, *(["sampled_at"] if "sampled_at" in frame else [])]
    normalized = frame[columns].copy()
    normalized["expiration_date"] = pd.to_datetime(
        normalized["expiration_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    normalized["strike"] = pd.to_numeric(normalized["strike"], errors="coerce")
    normalized["open_interest"] = pd.to_numeric(normalized["open_interest"], errors="coerce")
    normalized["underlying_price"] = pd.to_numeric(normalized["underlying_price"], errors="coerce")
    normalized["contract_type"] = normalized["contract_type"].astype(str).str.upper()
    return normalized.dropna(subset=[*_CONTRACT_KEYS, "open_interest", "strike"])


def compute_oi_changes(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    """Return OI changes for contracts present in both daily chains.

    Newly listed or otherwise unmatched contracts are omitted because their
    prior-day OI is unknown; treating missing data as zero would create false
    large changes.
    """
    current_rows = _normalize_chain(current)
    previous_rows = _normalize_chain(previous)
    if current_rows.empty or previous_rows.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    previous_rows = previous_rows[[*_CONTRACT_KEYS, "open_interest"]].rename(
        columns={"open_interest": "previous_open_interest"}
    )
    matched = current_rows.merge(
        previous_rows,
        on=_CONTRACT_KEYS,
        how="inner",
        validate="one_to_one",
    )
    matched["open_interest"] -= matched.pop("previous_open_interest")
    result_columns = [*_OUTPUT_COLUMNS, *(["sampled_at"] if "sampled_at" in matched else [])]
    return matched[result_columns]


def build_historical_oi_change_frames(
    frames: list[pd.DataFrame],
    sample_datetimes: list[datetime],
    before_date: date,
) -> tuple[list[pd.DataFrame], list[datetime]]:
    """Build daily changes for adjacent archived sample dates before *before_date*."""
    dated_frames = sorted(zip(sample_datetimes, frames, strict=False), key=lambda item: item[0])
    changes: list[pd.DataFrame] = []
    change_datetimes: list[datetime] = []
    previous: tuple[datetime, pd.DataFrame] | None = None

    for sampled_at, frame in dated_frames:
        sample_date = sampled_at.astimezone(_CHICAGO).date()
        if sample_date >= before_date:
            continue
        if previous is not None:
            previous_date, previous_frame = previous
            if previous_date.astimezone(_CHICAGO).date() < sample_date:
                delta = compute_oi_changes(frame, previous_frame)
                if not delta.empty:
                    for _, expiry_delta in delta.groupby("expiration_date", sort=False):
                        changes.append(expiry_delta.reset_index(drop=True))
                        if "sampled_at" in expiry_delta:
                            expiry_sampled_at = pd.to_datetime(
                                expiry_delta["sampled_at"], utc=True
                            ).min()
                            change_datetimes.append(expiry_sampled_at.to_pydatetime())
                        else:
                            change_datetimes.append(sampled_at)
        previous = (sampled_at, frame)

    return changes, change_datetimes


def compute_current_oi_changes(
    current_snapshots: dict[date, pd.DataFrame],
    previous_frame: pd.DataFrame,
) -> dict[date, pd.DataFrame]:
    """Compare the current chain for each expiry with its previous daily chain."""
    changes: dict[date, pd.DataFrame] = {}
    for expiry, current_frame in current_snapshots.items():
        delta = compute_oi_changes(current_frame, previous_frame)
        if not delta.empty:
            changes[expiry] = delta
    return changes
