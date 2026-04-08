"""Data-cleaning pipeline and optimization-node generation.

Flow:
    raw CSV → filter_active → validate → build_stop_registry
             → build_optimization_nodes → attach time windows
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Business-rule constants ────────────────────────────────────────
TIME_WINDOW_SLACK_MIN = 5       # ±5 minutes around requested time
DEFAULT_SERVICE_TIME_MIN = 3    # boarding / alighting service time
REHABUS_SPEED_FACTOR = 1.5     # applied to Google Maps durations


# ── Step 1: filter & clean ─────────────────────────────────────────

def filter_active_passengers(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only active passengers with valid coordinates & times."""
    before = len(df)
    out = df.copy()
    out = out[out["is_active"] == True]  # noqa: E712

    required_cols = [
        "board_lat", "board_lng", "alight_lat", "alight_lng",
        "board_time_minutes", "alight_time_minutes",
        "passenger_type", "purpose", "existing_route",
    ]
    for col in required_cols:
        out = out.dropna(subset=[col])

    out = out[
        (out["board_lat"].between(22.1, 22.6))
        & (out["board_lng"].between(113.8, 114.4))
        & (out["alight_lat"].between(22.1, 22.6))
        & (out["alight_lng"].between(113.8, 114.4))
    ]

    after = len(out)
    logger.info("filter_active_passengers: %d → %d rows (dropped %d)", before, after, before - after)
    return out.reset_index(drop=True)


# ── Step 2: stop registry ──────────────────────────────────────────

def build_stop_registry(df: pd.DataFrame) -> pd.DataFrame:
    """Extract unique stops with IDs from boarding + alighting locations.

    Returns DataFrame with columns:
        stop_id, stop_name, lat, lng, stop_type
    """
    board = (
        df[["board_stop", "board_lat", "board_lng"]]
        .drop_duplicates(subset=["board_stop"])
        .rename(columns={"board_stop": "stop_name", "board_lat": "lat", "board_lng": "lng"})
    )
    board["stop_type"] = "board"

    alight = (
        df[["alight_stop", "alight_lat", "alight_lng"]]
        .drop_duplicates(subset=["alight_stop"])
        .rename(columns={"alight_stop": "stop_name", "alight_lat": "lat", "alight_lng": "lng"})
    )
    alight["stop_type"] = "alight"

    combined = pd.concat([board, alight], ignore_index=True).drop_duplicates(subset=["stop_name"])
    combined = combined.reset_index(drop=True)
    combined["stop_id"] = ["S" + str(i).zfill(4) for i in range(len(combined))]
    return combined[["stop_id", "stop_name", "lat", "lng", "stop_type"]]


# ── Step 3 & 4: optimization nodes with time windows ──────────────

def build_optimization_nodes(
    df: pd.DataFrame,
    depot_lat: float,
    depot_lng: float,
) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Build the node table used by the VRPTW solver.

    Node layout (single-depot):
        index 0          → depot
        index 1, 2       → pickup & dropoff for passenger 1
        index 3, 4       → pickup & dropoff for passenger 2
        …

    Returns:
        nodes_df:  DataFrame with columns
            [node_id, node_type, passenger, lat, lng,
             tw_start, tw_end, wheelchair_demand, seated_demand, service_time]
        pickup_delivery_pairs:  list of (pickup_node_index, delivery_node_index)
    """
    rows: list[dict[str, Any]] = []
    pairs: list[tuple[int, int]] = []

    # Depot node
    rows.append(
        {
            "node_id": 0,
            "node_type": "depot",
            "passenger": None,
            "lat": depot_lat,
            "lng": depot_lng,
            "tw_start": 0,
            "tw_end": 1440,
            "wheelchair_demand": 0,
            "seated_demand": 0,
            "service_time": 0,
        }
    )

    node_idx = 1
    for _, row in df.iterrows():
        board_tw_start = max(0, int(row["board_time_minutes"]) - TIME_WINDOW_SLACK_MIN)
        board_tw_end = min(1440, int(row["board_time_minutes"]) + TIME_WINDOW_SLACK_MIN)
        alight_tw_start = max(0, int(row["alight_time_minutes"]) - TIME_WINDOW_SLACK_MIN)
        alight_tw_end = min(1440, int(row["alight_time_minutes"]) + TIME_WINDOW_SLACK_MIN)

        wc = int(row.get("is_wheelchair", 0))
        nwc = int(row.get("is_non_wheelchair", 0))

        pickup_idx = node_idx
        delivery_idx = node_idx + 1

        # Pickup node
        rows.append(
            {
                "node_id": pickup_idx,
                "node_type": "pickup",
                "passenger": row["passenger"],
                "lat": row["board_lat"],
                "lng": row["board_lng"],
                "tw_start": board_tw_start,
                "tw_end": board_tw_end,
                "wheelchair_demand": wc,
                "seated_demand": nwc,
                "service_time": DEFAULT_SERVICE_TIME_MIN,
            }
        )

        # Delivery node (demands are negative → unload)
        rows.append(
            {
                "node_id": delivery_idx,
                "node_type": "dropoff",
                "passenger": row["passenger"],
                "lat": row["alight_lat"],
                "lng": row["alight_lng"],
                "tw_start": alight_tw_start,
                "tw_end": alight_tw_end,
                "wheelchair_demand": -wc,
                "seated_demand": -nwc,
                "service_time": DEFAULT_SERVICE_TIME_MIN,
            }
        )

        pairs.append((pickup_idx, delivery_idx))
        node_idx += 2

    nodes_df = pd.DataFrame(rows)
    return nodes_df, pairs


# ── Helper: identify carer bundles ─────────────────────────────────

def identify_carer_bundles(df: pd.DataFrame) -> list[list[str]]:
    """Return groups of passengers that must ride together (user + carer).

    Convention in the CSV: a carer row has the same base name + '跟车' suffix
    and identical board/alight times.
    """
    bundles: list[list[str]] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        name = str(row["passenger"])
        if name in seen:
            continue
        if name.endswith("跟车"):
            base = name.replace("跟车", "")
            bundles.append(sorted({base, name}))
            seen.update({base, name})
        else:
            carer_name = name + "跟车"
            if carer_name in df["passenger"].values:
                bundles.append(sorted({name, carer_name}))
                seen.update({name, carer_name})
    return bundles
