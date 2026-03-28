"""Google Maps Routes API integration with Rehabus speed-factor correction.

Uses the *Compute Route Matrix* endpoint (NOT the legacy Distance Matrix API).
Endpoint: POST https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix

Environment variable required:
    GOOGLE_MAPS_API_KEY
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
DEFAULT_REHABUS_SPEED_FACTOR = 1.5
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # seconds, doubled each retry
_BATCH_SIZE = 25     # Google allows up to 25 origins × 25 destinations per call


# ── Public helpers ─────────────────────────────────────────────────

def apply_rehabus_speed_factor(
    google_duration_minutes: float,
    factor: float = DEFAULT_REHABUS_SPEED_FACTOR,
) -> float:
    """Rehabus vehicles are slower than private cars.

    projected_travel_time = google_duration_minutes × factor (default 1.5)
    """
    return google_duration_minutes * factor


def get_api_key() -> str | None:
    return os.getenv("GOOGLE_MAPS_API_KEY")


# ── Single route ───────────────────────────────────────────────────

def get_single_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    factor: float = DEFAULT_REHABUS_SPEED_FACTOR,
) -> dict[str, Any] | None:
    """Compute travel info between a single OD pair.

    Returns dict with keys:
        distance_meters, google_duration_minutes, rehabus_duration_minutes,
        source, timestamp
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set — returning None")
        return None

    payload = {
        "origin": {
            "location": {
                "latLng": {"latitude": origin[0], "longitude": origin[1]},
            }
        },
        "destination": {
            "location": {
                "latLng": {"latitude": destination[0], "longitude": destination[1]},
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
        "Content-Type": "application/json",
    }

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            route = data.get("routes", [{}])[0]
            dist_m = route.get("distanceMeters", 0)
            dur_str = route.get("duration", "0s")
            dur_sec = int(dur_str.rstrip("s"))
            google_min = dur_sec / 60.0
            return {
                "distance_meters": dist_m,
                "google_duration_minutes": round(google_min, 2),
                "rehabus_duration_minutes": round(apply_rehabus_speed_factor(google_min, factor), 2),
                "source": "google_routes_api",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as exc:
            logger.warning("get_single_route attempt %d failed: %s", attempt, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF * attempt)
    return None


# ── Route matrix (batch) ──────────────────────────────────────────

def get_route_matrix(
    origins: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
    factor: float = DEFAULT_REHABUS_SPEED_FACTOR,
) -> list[dict[str, Any]]:
    """Compute travel times for all origin-destination pairs.

    Returns a list of dicts, one per OD pair:
        origin_index, destination_index, distance_meters,
        google_duration_minutes, rehabus_duration_minutes,
        source, timestamp
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set — returning empty list")
        return []

    def _waypoint(lat: float, lng: float) -> dict:
        return {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}

    results: list[dict[str, Any]] = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    # Batch into BATCH_SIZE chunks to stay within API limits
    for o_start in range(0, len(origins), _BATCH_SIZE):
        o_batch = origins[o_start : o_start + _BATCH_SIZE]
        for d_start in range(0, len(destinations), _BATCH_SIZE):
            d_batch = destinations[d_start : d_start + _BATCH_SIZE]

            payload = {
                "origins": [_waypoint(lat, lng) for lat, lng in o_batch],
                "destinations": [_waypoint(lat, lng) for lat, lng in d_batch],
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
            }
            headers = {
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status,condition",
                "Content-Type": "application/json",
            }

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    resp = requests.post(ROUTE_MATRIX_URL, json=payload, headers=headers, timeout=60)
                    resp.raise_for_status()
                    elements = resp.json()
                    if not isinstance(elements, list):
                        elements = [elements]
                    for el in elements:
                        oi = el.get("originIndex", 0) + o_start
                        di = el.get("destinationIndex", 0) + d_start
                        dur_str = el.get("duration", "0s")
                        dur_sec = int(dur_str.rstrip("s")) if isinstance(dur_str, str) else 0
                        google_min = dur_sec / 60.0
                        results.append(
                            {
                                "origin_index": oi,
                                "destination_index": di,
                                "distance_meters": el.get("distanceMeters", 0),
                                "google_duration_minutes": round(google_min, 2),
                                "rehabus_duration_minutes": round(
                                    apply_rehabus_speed_factor(google_min, factor), 2
                                ),
                                "source": "google_routes_api",
                                "timestamp": ts,
                            }
                        )
                    break  # success
                except Exception as exc:
                    logger.warning("get_route_matrix batch attempt %d failed: %s", attempt, exc)
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_BACKOFF * attempt)

    return results
