"""Business-rule validators for Rehabus route optimization.

Every function returns a list of violation dicts:
    {"rule": str, "status": "pass"|"warning"|"violation", "detail": str, "route_id": str|None}
"""

from __future__ import annotations

import pandas as pd

# ── Constraint thresholds ──────────────────────────────────────────
MAX_TIME_WINDOW_SLACK = 5        # minutes
MAX_RIDE_TIME = 120              # per-passenger in-vehicle time
MAX_ROUTE_DURATION = 180         # per-route
MAX_WHEELCHAIR_ONBOARD = 5
MAX_SEATED_ONBOARD = 10
MIN_PASSENGERS_PER_ROUTE = 6
MAX_DUTY_SPREAD = 840            # 14 hours
MAX_DRIVING_PER_SHIFT = 660      # 11 hours
REFUELING_TIME = 15              # minutes appended at end of day


def _ok(rule: str, detail: str, route_id: str | None = None) -> dict:
    return {"rule": rule, "status": "pass", "detail": detail, "route_id": route_id}


def _warn(rule: str, detail: str, route_id: str | None = None) -> dict:
    return {"rule": rule, "status": "warning", "detail": detail, "route_id": route_id}


def _fail(rule: str, detail: str, route_id: str | None = None) -> dict:
    return {"rule": rule, "status": "violation", "detail": detail, "route_id": route_id}


# ── Per-route validators ──────────────────────────────────────────

def check_route_duration(route_id: str, duration_min: float) -> dict:
    rule = f"Route 总时长 (≤{MAX_ROUTE_DURATION} min)"
    if duration_min <= MAX_ROUTE_DURATION:
        return _ok(rule, f"{duration_min:.0f} min", route_id)
    return _fail(rule, f"{duration_min:.0f} min 超限", route_id)


def check_wheelchair_capacity(route_id: str, max_simultaneous_wc: int) -> dict:
    rule = f"轮椅容量 (≤{MAX_WHEELCHAIR_ONBOARD})"
    if max_simultaneous_wc <= MAX_WHEELCHAIR_ONBOARD:
        return _ok(rule, f"最大同时 {max_simultaneous_wc} 位", route_id)
    return _fail(rule, f"最大同时 {max_simultaneous_wc} 位 — 超限", route_id)


def check_seated_capacity(route_id: str, max_simultaneous_seat: int) -> dict:
    rule = f"座位容量 (≤{MAX_SEATED_ONBOARD})"
    if max_simultaneous_seat <= MAX_SEATED_ONBOARD:
        return _ok(rule, f"最大同时 {max_simultaneous_seat} 位", route_id)
    return _fail(rule, f"最大同时 {max_simultaneous_seat} 位 — 超限", route_id)


def check_minimum_load(route_id: str, passenger_count: int) -> dict:
    rule = f"最低装载 (≥{MIN_PASSENGERS_PER_ROUTE})"
    if passenger_count >= MIN_PASSENGERS_PER_ROUTE:
        return _ok(rule, f"{passenger_count} 名乘客", route_id)
    return _warn(rule, f"仅 {passenger_count} 名 — 建议合并", route_id)


def check_ride_time(route_id: str, passenger: str, ride_min: float) -> dict:
    rule = f"单乘客车程 (≤{MAX_RIDE_TIME} min)"
    if ride_min <= MAX_RIDE_TIME:
        return _ok(rule, f"{passenger}: {ride_min:.0f} min", route_id)
    return _fail(rule, f"{passenger}: {ride_min:.0f} min 超限", route_id)


def check_time_window(route_id: str, passenger: str, actual_min: float, requested_min: float) -> dict:
    rule = f"时间窗 (±{MAX_TIME_WINDOW_SLACK} min)"
    diff = abs(actual_min - requested_min)
    if diff <= MAX_TIME_WINDOW_SLACK:
        return _ok(rule, f"{passenger}: 偏差 {diff:.0f} min", route_id)
    return _fail(rule, f"{passenger}: 偏差 {diff:.0f} min 超限", route_id)


# ── Duty-level validators ─────────────────────────────────────────

def check_depot_consistency(route_id: str, start_depot: str, end_depot: str) -> dict:
    rule = "Depot 一致性"
    if start_depot == end_depot:
        return _ok(rule, f"{start_depot}", route_id)
    return _fail(rule, f"起始 {start_depot} ≠ 签收 {end_depot}", route_id)


def check_duty_spread(duty_id: str, spread_min: float) -> dict:
    rule = f"值勤时间 (≤{MAX_DUTY_SPREAD // 60}h)"
    if spread_min <= MAX_DUTY_SPREAD:
        return _ok(rule, f"{spread_min:.0f} min", duty_id)
    return _fail(rule, f"{spread_min:.0f} min 超限", duty_id)


def check_driving_hours(duty_id: str, driving_min: float) -> dict:
    rule = f"驾驶时间 (≤{MAX_DRIVING_PER_SHIFT // 60}h / shift)"
    if driving_min <= MAX_DRIVING_PER_SHIFT:
        return _ok(rule, f"{driving_min:.0f} min", duty_id)
    return _fail(rule, f"{driving_min:.0f} min 超限", duty_id)


def check_refueling(duty_id: str, includes_refueling: bool) -> dict:
    rule = f"加油时间 ({REFUELING_TIME} min / day)"
    if includes_refueling:
        return _ok(rule, "已预留", duty_id)
    return _warn(rule, "尚未计入", duty_id)


# ── Aggregate: validate a full solution ────────────────────────────

def validate_solution(route_results: pd.DataFrame) -> list[dict]:
    """Run all applicable validators on a solution DataFrame.

    Expected columns:
        route_id, passenger_count, wheelchair_count, seated_count,
        estimated_duration, depot_start, depot_end
    """
    checks: list[dict] = []
    for _, r in route_results.iterrows():
        rid = str(r.get("route_id", "?"))
        checks.append(check_route_duration(rid, r.get("estimated_duration", 0)))
        checks.append(check_wheelchair_capacity(rid, r.get("wheelchair_count", 0)))
        checks.append(check_seated_capacity(rid, r.get("seated_count", 0)))
        checks.append(check_minimum_load(rid, r.get("passenger_count", 0)))
        checks.append(
            check_depot_consistency(
                rid,
                str(r.get("depot_start", "")),
                str(r.get("depot_end", r.get("depot_start", ""))),
            )
        )
    return checks
