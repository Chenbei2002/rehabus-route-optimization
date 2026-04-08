"""Scenario builder — split passengers into optimization groups.

Two simulation approaches:
    A.  All-Purpose — every active passenger enters one big pool.
    B.  Separate-Purpose — passengers are grouped by trip purpose first:
            Group 1: school (上學) / training (訓練) / rehabilitation (治療, 就診)
            Group 2: everything else (work 工作, other)
        Each group is optimized independently.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Purpose categories used for Separate-Purpose approach
_GROUP_1_PURPOSES = {"上學", "訓練", "治療", "就診"}


def build_scenario(
    df: pd.DataFrame,
    mode: str = "all_purpose",
) -> dict[str, pd.DataFrame]:
    """Return a dict of demand-group name → passenger DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned, active passengers (output of preprocess.filter_active_passengers).
    mode : str
        ``"all_purpose"`` or ``"separate_purpose"``.

    Returns
    -------
    dict
        ``{"all": df}`` for all-purpose, or
        ``{"school_training_rehab": df1, "other": df2}`` for separate-purpose.
    """
    if mode == "all_purpose":
        logger.info("Scenario ALL-PURPOSE: %d passengers in 1 group", len(df))
        return {"all": df}

    if mode == "separate_purpose":
        mask = df["purpose"].isin(_GROUP_1_PURPOSES)
        g1 = df[mask].reset_index(drop=True)
        g2 = df[~mask].reset_index(drop=True)
        logger.info(
            "Scenario SEPARATE-PURPOSE: group_1 (school/training/rehab) = %d, "
            "group_2 (other) = %d",
            len(g1), len(g2),
        )
        return {"school_training_rehab": g1, "other": g2}

    raise ValueError(f"Unknown scenario mode: {mode!r}")


def assign_depot(
    df: pd.DataFrame,
    depot_df: pd.DataFrame,
) -> pd.DataFrame:
    """Assign each passenger to the nearest depot (by Haversine to board stop).

    Adds column ``assigned_depot`` to the returned DataFrame.
    """
    from services.matrix_builder import _haversine_km

    depots = depot_df[["depot_code", "lat", "lon"]].dropna().to_dict("records")
    assignments = []
    for _, row in df.iterrows():
        best_code = depots[0]["depot_code"]
        best_dist = float("inf")
        for d in depots:
            dist = _haversine_km(row["board_lat"], row["board_lng"], d["lat"], d["lon"])
            if dist < best_dist:
                best_dist = dist
                best_code = d["depot_code"]
        assignments.append(best_code)
    out = df.copy()
    out["assigned_depot"] = assignments
    return out
