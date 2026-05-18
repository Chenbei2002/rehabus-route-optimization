"""Build travel-time matrices for the VRPTW solver.

Strategy:
    1. Try to load a cached matrix from data/travel_time_matrix.parquet.
    2. For missing OD pairs, call Google Maps Routes API (if API key present).
    3. Fall back to Haversine-based estimate for any remaining gaps.
    4. All durations carry the Rehabus speed factor (×1.5).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from services.google_maps_service import (
    DEFAULT_REHABUS_SPEED_FACTOR,
    apply_rehabus_speed_factor,
    get_route_matrix,
    get_api_key,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "travel_time_matrix.parquet"

# Average Rehabus speed used in Haversine fallback: ~20 km/h
_HAVERSINE_AVG_SPEED_KMH = 20.0


# ── Haversine fallback ─────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    rlat1, rlng1, rlat2, rlng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = np.sin(dlat / 2) ** 2 + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlng / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def haversine_travel_time_minutes(
    lat1: float, lng1: float, lat2: float, lng2: float,
    speed_kmh: float = _HAVERSINE_AVG_SPEED_KMH,
) -> float:
    """Estimated travel time in minutes using Haversine + constant speed.

    Note: this already reflects Rehabus speed (not private-car speed).
    """
    dist = _haversine_km(lat1, lng1, lat2, lng2)
    return (dist / speed_kmh) * 60.0 if speed_kmh > 0 else 0.0


# ── Cache I/O ──────────────────────────────────────────────────────

def load_cached_matrix() -> pd.DataFrame | None:
    if CACHE_FILE.exists():
        logger.info("Loading cached matrix from %s", CACHE_FILE)
        return pd.read_parquet(CACHE_FILE)
    return None


def save_matrix_cache(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_FILE, index=False)
    logger.info("Saved matrix cache → %s (%d rows)", CACHE_FILE, len(df))


# ── Build node-level time matrix ──────────────────────────────────

def build_time_matrix(
    nodes_df: pd.DataFrame,
    use_google: bool = True,
) -> np.ndarray:
    """Return an N×N numpy array of travel times (minutes, Rehabus-adjusted).

    nodes_df must contain columns: lat, lng
    Uses vectorised Haversine for speed.
    """
    n = len(nodes_df)
    lats = np.radians(nodes_df["lat"].values)
    lngs = np.radians(nodes_df["lng"].values)

    # Vectorised Haversine → distance matrix in km
    dlat = lats[:, None] - lats[None, :]
    dlng = lngs[:, None] - lngs[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lats[:, None]) * np.cos(lats[None, :]) * np.sin(dlng / 2) ** 2
    dist_km = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    # Convert to travel-time minutes (using Rehabus-effective speed)
    matrix = (dist_km / _HAVERSINE_AVG_SPEED_KMH) * 60.0
    np.fill_diagonal(matrix, 0.0)

    # Overlay Google Maps data if API key is present and caller opts in
    if use_google and get_api_key():
        _overlay_google_matrix(nodes_df, matrix)

    # Add service_time at destination node
    if "service_time" in nodes_df.columns:
        svc = nodes_df["service_time"].fillna(0).values.astype(np.float64)
        matrix += svc[None, :]

    return np.rint(matrix).astype(int)


def _overlay_google_matrix(nodes_df: pd.DataFrame, matrix: np.ndarray) -> None:
    """Replace Haversine cells with Google Maps durations where available."""
    cached = load_cached_matrix()
    lats = nodes_df["lat"].values.tolist()
    lngs = nodes_df["lng"].values.tolist()

    if cached is not None and not cached.empty:
        # Build lookup from cached data (rounded coords as key)
        lookup: dict[tuple, float] = {}
        for _, row in cached.iterrows():
            key = (
                round(row["origin_lat"], 5),
                round(row["origin_lng"], 5),
                round(row["dest_lat"], 5),
                round(row["dest_lng"], 5),
            )
            lookup[key] = row["rehabus_duration_minutes"]

        hits = 0
        for i in range(len(nodes_df)):
            for j in range(len(nodes_df)):
                if i == j:
                    continue
                key = (round(lats[i], 5), round(lngs[i], 5), round(lats[j], 5), round(lngs[j], 5))
                if key in lookup:
                    matrix[i, j] = lookup[key]
                    hits += 1
        logger.info("Cache overlay: %d / %d cells", hits, len(nodes_df) ** 2)

    # For a production run, request missing OD pairs from Google here.
    # Skipped in MVP to avoid large API costs; use haversine for the rest.


def build_time_matrix_for_stops(
    stop_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return a long-form DataFrame of stop-to-stop travel times.

    Useful for caching and inspection. Columns:
        origin_stop, origin_lat, origin_lng,
        dest_stop, dest_lat, dest_lng,
        haversine_km, haversine_minutes, rehabus_duration_minutes
    """
    rows = []
    stops = stop_df.to_dict("records")
    for o in stops:
        for d in stops:
            if o["stop_id"] == d["stop_id"]:
                continue
            dist = _haversine_km(o["lat"], o["lng"], d["lat"], d["lng"])
            hav_min = (dist / _HAVERSINE_AVG_SPEED_KMH) * 60
            rows.append(
                {
                    "origin_stop": o["stop_id"],
                    "origin_lat": o["lat"],
                    "origin_lng": o["lng"],
                    "dest_stop": d["stop_id"],
                    "dest_lat": d["lat"],
                    "dest_lng": d["lng"],
                    "haversine_km": round(dist, 3),
                    "haversine_minutes": round(hav_min, 2),
                    "rehabus_duration_minutes": round(
                        apply_rehabus_speed_factor(hav_min / DEFAULT_REHABUS_SPEED_FACTOR), 2
                    ),
                }
            )
    return pd.DataFrame(rows)
