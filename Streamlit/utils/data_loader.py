"""Data loading with Streamlit caching.

Supports both project-root layout and data/ subdirectory layout:
    ./passenger_input_clean.csv   OR   ./data/passenger_input_clean.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = APP_DIR.parent


def _find(name: str) -> Path:
    """Locate a data file across app/repo candidate directories."""
    candidates = [
        APP_DIR / name,
        APP_DIR / "data" / name,
        APP_DIR / "output_data" / name,
        REPO_DIR / name,
        REPO_DIR / "data" / name,
        REPO_DIR / "output_data" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Cannot find {name}. Searched: {searched}")


# ── Passenger data ────────────────────────────────────────────────

@st.cache_data
def load_passenger_data() -> pd.DataFrame:
    path = _find("passenger_input_clean.csv")
    df = pd.read_csv(path)

    numeric_cols = [
        "board_time_minutes", "alight_time_minutes", "trip_duration_minutes_est",
        "board_lat", "board_lng", "alight_lat", "alight_lng",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in ("is_wheelchair", "is_non_wheelchair"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    if "is_active" in df.columns:
        df["is_active"] = df["is_active"].fillna(False)

    return df


# ── Parking / depot data ─────────────────────────────────────────

@st.cache_data
def load_parking_data() -> pd.DataFrame:
    path = _find("parking_data.csv")
    df = pd.read_csv(path)
    df.columns = ["depot_code", "depot_name", "lat", "lon", "max_vehicles"]
    df["max_vehicles"] = pd.to_numeric(df["max_vehicles"], errors="coerce").fillna(0).astype(int)
    return df


# ── Optimization outputs (if available) ───────────────────────────

@st.cache_data
def load_optimization_output() -> pd.DataFrame | None:
    try:
        path = _find("optimization_output.csv")
        return pd.read_csv(path)
    except FileNotFoundError:
        return None


@st.cache_data
def load_route_summary_output() -> pd.DataFrame | None:
    try:
        path = _find("route_summary.csv")
        return pd.read_csv(path)
    except FileNotFoundError:
        return None


# ── Filter helper ─────────────────────────────────────────────────

def apply_filters(
    df: pd.DataFrame,
    passenger_types: list | None = None,
    purposes: list | None = None,
    districts: list | None = None,
    routes: list | None = None,
    day_patterns: list | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    if passenger_types:
        filtered = filtered[filtered["passenger_type"].isin(passenger_types)]
    if purposes:
        filtered = filtered[filtered["purpose"].isin(purposes)]
    if districts:
        filtered = filtered[
            filtered["board_district"].isin(districts)
            | filtered["alight_district"].isin(districts)
        ]
    if routes:
        filtered = filtered[filtered["existing_route"].isin(routes)]
    if day_patterns:
        filtered = filtered[filtered["day_pattern"].astype(str).isin([str(d) for d in day_patterns])]
    return filtered


# ── Route summary aggregator ──────────────────────────────────────

@st.cache_data
def get_route_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("existing_route")
        .agg(
            passenger_count=("passenger", "nunique"),
            wheelchair_count=("is_wheelchair", "sum"),
            seated_count=("is_non_wheelchair", "sum"),
            unique_board_stops=("board_stop", "nunique"),
            unique_alight_stops=("alight_stop", "nunique"),
            avg_trip_duration=("trip_duration_minutes_est", "mean"),
            purposes=("purpose", lambda x: ", ".join(sorted(x.dropna().unique()))),
        )
        .reset_index()
        .rename(columns={"existing_route": "route"})
        .sort_values("passenger_count", ascending=False)
    )
    summary["avg_trip_duration"] = summary["avg_trip_duration"].round(1)
    return summary
