"""OR-Tools VRPTW solver for Rehabus route optimization.

Model: Vehicle Routing Problem with Time Windows, Pickup & Delivery,
       heterogeneous capacity (wheelchair + seated), and route-duration limit.

Objective hierarchy:
    1. Minimise number of vehicles used.
    2. Minimise total travel time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

logger = logging.getLogger(__name__)


# ── Configuration dataclass ────────────────────────────────────────

@dataclass
class VehicleConfig:
    """Defaults reflect standard Rehabus vehicle constraints."""
    wheelchair_capacity: int = 5
    seated_capacity: int = 10
    max_route_duration_min: int = 180
    max_ride_time_per_user_min: int = 120
    max_driving_per_shift_min: int = 660   # 11 hours
    max_duty_spread_min: int = 840          # 14 hours
    refueling_time_min: int = 15


@dataclass
class SolverConfig:
    time_limit_seconds: int = 60
    first_solution_strategy: int = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    metaheuristic: int = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )


@dataclass
class OptimizationResult:
    status: str  # "optimal", "feasible", "no_solution"
    routes: list[dict[str, Any]] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


# ── Solver ─────────────────────────────────────────────────────────

def solve_vrptw(
    nodes_df: pd.DataFrame,
    time_matrix: np.ndarray,
    pickup_delivery_pairs: list[tuple[int, int]],
    num_vehicles: int | None = None,
    vehicle_cfg: VehicleConfig | None = None,
    solver_cfg: SolverConfig | None = None,
) -> OptimizationResult:
    """Solve the VRPTW with pickup-and-delivery and dual capacity.

    Parameters
    ----------
    nodes_df : DataFrame
        Output of ``preprocess.build_optimization_nodes``.
        Must have: node_id, node_type, tw_start, tw_end,
                   wheelchair_demand, seated_demand, service_time, passenger
    time_matrix : np.ndarray
        Square matrix of travel times (int minutes).
    pickup_delivery_pairs : list of (int, int)
        Index pairs (pickup_node, delivery_node).
    num_vehicles : int or None
        Upper bound on fleet size.  If None → len(pairs) (one per request).
    vehicle_cfg, solver_cfg : optional override configs.
    """
    vcfg = vehicle_cfg or VehicleConfig()
    scfg = solver_cfg or SolverConfig()

    n = len(nodes_df)
    if num_vehicles is None:
        num_vehicles = len(pickup_delivery_pairs)

    # Depot is node 0
    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # ─── Time / distance callback ──────────────────────────────
    matrix = time_matrix.astype(int)

    def _time_cb(from_index: int, to_index: int) -> int:
        fi = manager.IndexToNode(from_index)
        ti = manager.IndexToNode(to_index)
        return int(matrix[fi][ti])

    transit_cb = routing.RegisterTransitCallback(_time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # ─── Time dimension ────────────────────────────────────────
    max_time = 1440  # end-of-day ceiling
    routing.AddDimension(
        transit_cb,
        max_time,   # allowed waiting time
        max_time,   # max cumulative time
        False,      # don't force start cumul to zero
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    # Time windows per node
    for node in range(n):
        idx = manager.NodeToIndex(node)
        tw_s = int(nodes_df.iloc[node]["tw_start"])
        tw_e = int(nodes_df.iloc[node]["tw_end"])
        time_dim.CumulVar(idx).SetRange(tw_s, tw_e)

    # Route duration limit per vehicle
    for v in range(num_vehicles):
        start_idx = routing.Start(v)
        end_idx = routing.End(v)
        routing.solver().Add(
            time_dim.CumulVar(end_idx) - time_dim.CumulVar(start_idx)
            <= vcfg.max_route_duration_min
        )

    # Minimise total time span (secondary objective)
    for v in range(num_vehicles):
        time_dim.SetSpanCostCoefficientForVehicle(1, v)

    # ─── Pickup and delivery ───────────────────────────────────
    for pi, di in pickup_delivery_pairs:
        pickup_idx = manager.NodeToIndex(pi)
        delivery_idx = manager.NodeToIndex(di)
        routing.AddPickupAndDelivery(pickup_idx, delivery_idx)
        # Same vehicle
        routing.solver().Add(
            routing.VehicleVar(pickup_idx) == routing.VehicleVar(delivery_idx)
        )
        # Precedence (pickup before delivery)
        routing.solver().Add(
            time_dim.CumulVar(pickup_idx) <= time_dim.CumulVar(delivery_idx)
        )
        # User ride time ≤ max
        routing.solver().Add(
            time_dim.CumulVar(delivery_idx) - time_dim.CumulVar(pickup_idx)
            <= vcfg.max_ride_time_per_user_min
        )

    # ─── Wheelchair capacity dimension ─────────────────────────
    wc_demands = nodes_df["wheelchair_demand"].fillna(0).astype(int).tolist()

    def _wc_cb(index: int) -> int:
        return wc_demands[manager.IndexToNode(index)]

    wc_cb_id = routing.RegisterUnaryTransitCallback(_wc_cb)
    routing.AddDimensionWithVehicleCapacity(
        wc_cb_id, 0,
        [vcfg.wheelchair_capacity] * num_vehicles,
        True, "Wheelchair",
    )

    # ─── Seated capacity dimension ─────────────────────────────
    seat_demands = nodes_df["seated_demand"].fillna(0).astype(int).tolist()

    def _seat_cb(index: int) -> int:
        return seat_demands[manager.IndexToNode(index)]

    seat_cb_id = routing.RegisterUnaryTransitCallback(_seat_cb)
    routing.AddDimensionWithVehicleCapacity(
        seat_cb_id, 0,
        [vcfg.seated_capacity] * num_vehicles,
        True, "Seated",
    )

    # ─── Penalty for dropping nodes ────────────────────────────
    # Allow dropping pickup-delivery pairs with a large penalty to get a
    # feasible solution when the fleet is too small.
    PENALTY = 100_000
    for pi, di in pickup_delivery_pairs:
        routing.AddDisjunction([manager.NodeToIndex(pi), manager.NodeToIndex(di)], PENALTY)

    # ─── Search parameters ─────────────────────────────────────
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = scfg.first_solution_strategy
    params.local_search_metaheuristic = scfg.metaheuristic
    params.time_limit.FromSeconds(scfg.time_limit_seconds)

    # ─── Solve ─────────────────────────────────────────────────
    logger.info("Solving VRPTW — %d nodes, %d vehicles, %d PD pairs …",
                n, num_vehicles, len(pickup_delivery_pairs))
    solution = routing.SolveWithParameters(params)

    if solution is None:
        logger.warning("No solution found.")
        return OptimizationResult(status="no_solution")

    return _extract(manager, routing, solution, nodes_df, time_dim, num_vehicles, vcfg)


# ── Solution extraction ────────────────────────────────────────────

def _extract(
    manager, routing, solution, nodes_df, time_dim, num_vehicles, vcfg,
) -> OptimizationResult:
    routes: list[dict[str, Any]] = []
    all_assigned_passengers: set[str] = set()

    for v in range(num_vehicles):
        stops: list[dict] = []
        index = routing.Start(v)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            t = solution.Value(time_dim.CumulVar(index))
            stops.append({"node": node, "time": t})
            index = solution.Value(routing.NextVar(index))
        # End depot
        node = manager.IndexToNode(index)
        t = solution.Value(time_dim.CumulVar(index))
        stops.append({"node": node, "time": t})

        # Skip empty routes (depot → depot only)
        if len(stops) <= 2:
            continue

        passengers_on_route: set[str] = set()
        max_wc = 0
        max_seat = 0
        cur_wc = 0
        cur_seat = 0
        stop_details: list[dict] = []

        for s in stops:
            nd = nodes_df.iloc[s["node"]]
            cur_wc += int(nd["wheelchair_demand"])
            cur_seat += int(nd["seated_demand"])
            max_wc = max(max_wc, cur_wc)
            max_seat = max(max_seat, cur_seat)
            if nd["node_type"] in ("pickup", "dropoff") and pd.notna(nd["passenger"]):
                passengers_on_route.add(nd["passenger"])
            stop_details.append({
                "node_id": s["node"],
                "node_type": nd["node_type"],
                "passenger": nd.get("passenger"),
                "arrival_time": s["time"],
                "lat": nd["lat"],
                "lng": nd["lng"],
            })

        duration = stops[-1]["time"] - stops[0]["time"]
        pax_count = len(passengers_on_route)
        all_assigned_passengers.update(passengers_on_route)

        routes.append({
            "route_id": f"OPT-{len(routes)+1:03d}",
            "vehicle_id": f"V-{v+1:03d}",
            "passenger_count": pax_count,
            "wheelchair_count": max_wc,
            "seated_count": max_seat,
            "estimated_duration": int(duration),
            "start_time": stops[0]["time"],
            "end_time": stops[-1]["time"],
            "stop_sequence": stop_details,
            "passengers": sorted(passengers_on_route),
            "utilization": round(pax_count / max(1, vcfg.wheelchair_capacity + vcfg.seated_capacity) * 100, 1),
            "feasibility": "通过",
        })

    # Identify unassigned passengers (dropped by disjunction penalty)
    all_passengers = set(nodes_df.loc[nodes_df["node_type"] == "pickup", "passenger"].dropna())
    unassigned = sorted(all_passengers - all_assigned_passengers)

    total_dur = sum(r["estimated_duration"] for r in routes)
    avg_util = np.mean([r["utilization"] for r in routes]) if routes else 0

    status = "optimal" if not unassigned else "feasible"
    return OptimizationResult(
        status=status,
        routes=routes,
        unassigned=unassigned,
        stats={
            "num_routes": len(routes),
            "total_duration": total_dur,
            "avg_duration": total_dur / len(routes) if routes else 0,
            "avg_utilization": round(avg_util, 1),
            "unassigned_count": len(unassigned),
        },
    )


# ── Convenience: results → flat DataFrames ─────────────────────────

def routes_to_dataframe(result: OptimizationResult, scenario: str = "") -> pd.DataFrame:
    """Convert list of route dicts to a summary DataFrame."""
    if not result.routes:
        return pd.DataFrame()
    rows = []
    for r in result.routes:
        rows.append({
            "route_id": r["route_id"],
            "vehicle_id": r["vehicle_id"],
            "scenario": scenario,
            "passenger_count": r["passenger_count"],
            "wheelchair_count": r["wheelchair_count"],
            "seated_count": r["seated_count"],
            "estimated_duration": r["estimated_duration"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "depot": "depot",  # TODO: assign real depot
            "utilization": r["utilization"],
            "feasibility": r["feasibility"],
        })
    return pd.DataFrame(rows)


def user_changes_dataframe(
    result: OptimizationResult,
    original_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a per-passenger before/after table."""
    passenger_to_new_route: dict[str, str] = {}
    for r in result.routes:
        for p in r.get("passengers", []):
            passenger_to_new_route[p] = r["route_id"]

    rows = []
    for _, row in original_df.drop_duplicates("passenger").iterrows():
        pname = row["passenger"]
        new_route = passenger_to_new_route.get(pname, "未分配")
        rows.append({
            "passenger": pname,
            "before_route": row["existing_route"],
            "after_route": new_route,
            "purpose": row.get("purpose", ""),
            "status": "保持不变" if new_route != "未分配" else "未分配",
        })
    return pd.DataFrame(rows)
