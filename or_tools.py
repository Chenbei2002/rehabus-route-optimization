#!/usr/bin/env python3
"""
Rehabus VRPTW + Pickup/Delivery (OR-Tools)

数据来源:
  - passenger_input_clean_2.csv（项目根目录）
  - parking_data/ 下所有 *.csv，若不存在则使用 parking_data.csv

行程时间:
  - 默认使用 services.matrix_builder（Haversine + Rehabus 车速，与 Dashboard 一致）
  - 若设置 GOOGLE_MAPS_API_KEY，可用 --google-depot-edges 对「各 depot → 其余节点」批量调用
    Google Routes API（Compute Route Matrix）并乘以 Rehabus 系数 1.5

多 depot:
  - 按 parking 表中「Max number of vehicle allocated」生成车辆槽位，每辆车从同一 depot 出发并返回

注意: 全量乘客（约 2500+ 请求）节点数极大，求解可能很慢或内存不足；请先用 --limit 小规模验证。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# 项目根目录（保证可 import services）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.google_maps_service import get_api_key, get_route_matrix  # noqa: E402
from services.matrix_builder import build_time_matrix  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Rehabus 业务参数（与 validators / optimization_service 对齐）────────────────
TIME_WINDOW_SLACK_MIN = 5       # 上下车 ±5 分钟
SERVICE_TIME_MIN = 5
MAX_ROUTE_DURATION_MIN = 180    # 单条路线 ≤ 3 小时（见下方说明，需单独维度才能硬约束）
MAX_RIDE_TIME_MIN = 120         # 单车程 ≤ 2 小时
WHEELCHAIR_CAPACITY = 5
SEAT_CAPACITY = 10
VEHICLE_FIXED_COST = 500_000    # 优先少用车辆（再优化行驶时间）
HORIZON_MIN = 24 * 60
WAIT_SLACK_MIN = 60             # 时间维允许等待（等时钟、等时间窗）
# 「Time」维度表示从午夜起的分钟数（时间窗）；全局上限必须 ≥ 任意节点 tw_end，不能用 180
TIME_DIMENSION_MAX = HORIZON_MIN + WAIT_SLACK_MIN


def load_parking_data(root: Path) -> pd.DataFrame:
    """读取 parking_data/ 下 CSV，否则 parking_data.csv。"""
    folder = root / "parking_data"
    frames: list[pd.DataFrame] = []
    if folder.is_dir():
        for p in sorted(folder.glob("*.csv")):
            frames.append(pd.read_csv(p))
    if not frames:
        csv_path = root / "parking_data.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"未找到停车数据：请放置 {root / 'parking_data.csv'} 或在 {folder}/ 下放入 *.csv"
            )
        frames.append(pd.read_csv(csv_path))
    df = pd.concat(frames, ignore_index=True)
    df.columns = [str(c).strip() for c in df.columns]
    # 兼容首列名为 ABB. 等
    first = df.columns[0]
    if first.lower() not in ("depot_code", "code", "id"):
        df = df.rename(columns={first: "depot_code"})
    rename_map = {
        "lon": "lng",
        "longitude": "lng",
        "lat": "lat",
        "Max number of vehicle allocated": "max_vehicles",
        "max number of vehicle allocated": "max_vehicles",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})
    if "max_vehicles" not in df.columns:
        # 尝试最后一列数字列
        for c in df.columns:
            if "vehicle" in c.lower() or "allocated" in c.lower():
                df = df.rename(columns={c: "max_vehicles"})
                break
    if "max_vehicles" not in df.columns:
        raise ValueError("停车数据缺少容量列（期望 max_vehicles 或 Max number of vehicle allocated）")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df["max_vehicles"] = pd.to_numeric(df["max_vehicles"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["lat", "lng"]).loc[df["max_vehicles"] > 0].reset_index(drop=True)
    return df


def load_passengers(path: Path, limit: int | None) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].astype(str).str.strip()
    num_cols = [
        "board_lat", "board_lng", "alight_lat", "alight_lng",
        "board_time_minutes", "alight_time_minutes",
        "is_wheelchair", "is_non_wheelchair", "trip_duration_minutes_est",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    need = ["board_lat", "board_lng", "alight_lat", "alight_lng", "board_time_minutes", "alight_time_minutes"]
    df = df.dropna(subset=need).copy()
    df["is_wheelchair"] = df.get("is_wheelchair", 0).fillna(0).astype(int).clip(0, 1)
    df["is_non_wheelchair"] = df.get("is_non_wheelchair", 0).fillna(0).astype(int).clip(0, 1)
    df["trip_duration_minutes_est"] = df.get("trip_duration_minutes_est", 60).fillna(60)
    if limit is not None and limit > 0:
        df = df.head(limit).reset_index(drop=True)
    return df.reset_index(drop=True)


def clock_time_window(center_minutes: float, slack_min: int) -> tuple[int, int]:
    """将 board/alight 映射到 [0, HORIZON_MIN] 上的闭区间，且保证 lo <= hi。"""
    c = int(round(float(center_minutes)))
    c = max(0, min(HORIZON_MIN, c))
    lo = max(0, c - slack_min)
    hi = min(HORIZON_MIN, c + slack_min)
    if lo > hi:
        lo = hi
    return lo, hi


def refine_matrix_depot_edges_google(
    matrix: np.ndarray,
    nodes_meta: list[dict],
    depot_indices: list[int],
    batch: int = 25,
) -> np.ndarray:
    """用 Google Route Matrix 覆盖「depot → 任意节点」的行程时间（Rehabus 已在返回值中）。"""
    if not get_api_key():
        logger.warning("未设置 GOOGLE_MAPS_API_KEY，跳过 Google 细化")
        return matrix
    n = len(nodes_meta)
    dep_coords = [(nodes_meta[i]["lat"], nodes_meta[i]["lng"]) for i in depot_indices]
    svc = np.array([nodes_meta[j].get("service_time", 0) or 0 for j in range(n)], dtype=float)
    for d_start in range(0, n, batch):
        d_end = min(d_start + batch, n)
        dest_coords = [(nodes_meta[j]["lat"], nodes_meta[j]["lng"]) for j in range(d_start, d_end)]
        results = get_route_matrix(dep_coords, dest_coords)
        for r in results:
            oi = int(r.get("origin_index", 0))
            di_local = int(r.get("destination_index", 0))
            gi = depot_indices[oi]
            gj = d_start + di_local
            if gi < n and gj < n and gi != gj:
                rehab = float(r.get("rehabus_duration_minutes", 0))
                # 与 matrix_builder 一致：弧长含目的点服务时间
                matrix[gi, gj] = int(round(rehab + svc[gj]))
    logger.info("Google depot 边细化完成（depots=%d, batch=%d）", len(depot_indices), batch)
    return matrix


def build_nodes_and_meta(
    parking_df: pd.DataFrame,
    pax_df: pd.DataFrame,
) -> tuple[list[dict], dict[int, int], dict[int, int], list[int], list[str]]:
    """
    节点顺序: [depot_0 .. depot_{D-1}, pickup_0, dropoff_0, pickup_1, dropoff_1, ...]
    返回: nodes_meta, pickup_node_by_req, dropoff_node_by_req, depot_indices, depot_codes
    """
    nodes_meta: list[dict] = []
    depot_indices: list[int] = []
    depot_codes: list[str] = []

    for _, row in parking_df.iterrows():
        code = str(row.get("depot_code", row.get("Depot Name", len(depot_codes))))
        idx = len(nodes_meta)
        depot_indices.append(idx)
        depot_codes.append(code)
        nodes_meta.append({
            "node_type": "depot",
            "depot_code": code,
            "passenger": None,
            "request_idx": None,
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "tw_start": 0,
            "tw_end": HORIZON_MIN,
            "wheelchair_delta": 0,
            "seat_delta": 0,
            "service_time": 0,
        })

    pickup_node_by_req: dict[int, int] = {}
    dropoff_node_by_req: dict[int, int] = {}

    for req_idx, row in pax_df.iterrows():
        pid = row.get("passenger", req_idx)
        pickup_idx = len(nodes_meta)
        pickup_node_by_req[req_idx] = pickup_idx
        b_lo, b_hi = clock_time_window(row["board_time_minutes"], TIME_WINDOW_SLACK_MIN)
        a_lo, a_hi = clock_time_window(row["alight_time_minutes"], TIME_WINDOW_SLACK_MIN)
        nodes_meta.append({
            "node_type": "pickup",
            "depot_code": None,
            "passenger": pid,
            "request_idx": req_idx,
            "lat": float(row["board_lat"]),
            "lng": float(row["board_lng"]),
            "tw_start": b_lo,
            "tw_end": b_hi,
            "wheelchair_delta": int(row["is_wheelchair"]),
            "seat_delta": int(row["is_non_wheelchair"]),
            "service_time": SERVICE_TIME_MIN,
        })
        drop_idx = len(nodes_meta)
        dropoff_node_by_req[req_idx] = drop_idx
        nodes_meta.append({
            "node_type": "dropoff",
            "depot_code": None,
            "passenger": pid,
            "request_idx": req_idx,
            "lat": float(row["alight_lat"]),
            "lng": float(row["alight_lng"]),
            "tw_start": a_lo,
            "tw_end": a_hi,
            "wheelchair_delta": -int(row["is_wheelchair"]),
            "seat_delta": -int(row["is_non_wheelchair"]),
            "service_time": SERVICE_TIME_MIN,
        })

    return nodes_meta, pickup_node_by_req, dropoff_node_by_req, depot_indices, depot_codes


def meta_to_dataframe(nodes_meta: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({
        "lat": [m["lat"] for m in nodes_meta],
        "lng": [m["lng"] for m in nodes_meta],
        "service_time": [m.get("service_time", 0) for m in nodes_meta],
    })


def assign_vehicles_to_depots(parking_df: pd.DataFrame) -> list[int]:
    """每辆车对应一个 depot 节点下标（重复 depot 节点索引）。"""
    slots: list[int] = []
    node_offset = 0
    for _, row in parking_df.iterrows():
        cap = int(row["max_vehicles"])
        for _ in range(cap):
            slots.append(node_offset)
        node_offset += 1
    return slots


def solve(
    time_matrix: np.ndarray,
    nodes_meta: list[dict],
    pax_df: pd.DataFrame,
    pickup_node_by_req: dict[int, int],
    dropoff_node_by_req: dict[int, int],
    vehicle_depot_node: list[int],
    time_limit_sec: int,
) -> tuple[pywrapcp.RoutingIndexManager, pywrapcp.RoutingModel, object | None]:
    num_nodes = len(nodes_meta)
    num_vehicles = len(vehicle_depot_node)
    if num_vehicles < 1:
        raise ValueError("车辆数为 0，请检查 parking 容量")

    starts = vehicle_depot_node[:]
    ends = vehicle_depot_node[:]
    manager = pywrapcp.RoutingIndexManager(num_nodes, num_vehicles, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def time_cb(from_index: int, to_index: int) -> int:
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return int(time_matrix[i, j])

    transit_cb = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    for v in range(num_vehicles):
        routing.SetFixedCostOfVehicle(VEHICLE_FIXED_COST, v)

    routing.AddDimension(
        transit_cb,
        WAIT_SLACK_MIN,
        TIME_DIMENSION_MAX,
        False,
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for node_idx, meta in enumerate(nodes_meta):
        idx = manager.NodeToIndex(node_idx)
        time_dim.CumulVar(idx).SetRange(int(meta["tw_start"]), int(meta["tw_end"]))

    # 车库出发/回到车库：与 Time 维度上限一致
    for v in range(num_vehicles):
        for ix in (routing.Start(v), routing.End(v)):
            time_dim.CumulVar(ix).SetRange(0, TIME_DIMENSION_MAX)

    def wheelchair_cb(from_index: int) -> int:
        n = manager.IndexToNode(from_index)
        return int(nodes_meta[n]["wheelchair_delta"])

    w_cb = routing.RegisterUnaryTransitCallback(wheelchair_cb)
    routing.AddDimensionWithVehicleCapacity(
        w_cb,
        0,
        [WHEELCHAIR_CAPACITY] * num_vehicles,
        True,
        "Wheelchair",
    )

    def seat_cb(from_index: int) -> int:
        n = manager.IndexToNode(from_index)
        return int(nodes_meta[n]["seat_delta"])

    s_cb = routing.RegisterUnaryTransitCallback(seat_cb)
    routing.AddDimensionWithVehicleCapacity(
        s_cb,
        0,
        [SEAT_CAPACITY] * num_vehicles,
        True,
        "Seat",
    )

    for req_idx, row in pax_df.iterrows():
        p_idx = pickup_node_by_req[req_idx]
        d_idx = dropoff_node_by_req[req_idx]
        p_ix = manager.NodeToIndex(p_idx)
        d_ix = manager.NodeToIndex(d_idx)
        routing.AddPickupAndDelivery(p_ix, d_ix)
        routing.solver().Add(routing.VehicleVar(p_ix) == routing.VehicleVar(d_ix))
        routing.solver().Add(time_dim.CumulVar(p_ix) <= time_dim.CumulVar(d_ix))
        max_ride = min(MAX_RIDE_TIME_MIN, int(row["trip_duration_minutes_est"]) + 30)
        max_ride = min(max_ride, MAX_RIDE_TIME_MIN)
        routing.solver().Add(
            time_dim.CumulVar(d_ix) - time_dim.CumulVar(p_ix) <= max_ride
        )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_sec

    solution = routing.SolveWithParameters(params)
    return manager, routing, solution


def solution_to_dataframes(
    manager: pywrapcp.RoutingIndexManager,
    routing: pywrapcp.RoutingModel,
    solution,
    nodes_meta: list[dict],
    vehicle_depot_node: list[int],
    depot_codes: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    time_dim = routing.GetDimensionOrDie("Time")
    w_dim = routing.GetDimensionOrDie("Wheelchair")
    s_dim = routing.GetDimensionOrDie("Seat")

    route_rows: list[dict] = []
    stop_rows: list[dict] = []

    for v in range(routing.vehicles()):
        index = routing.Start(v)
        seq = 0
        dep_node = vehicle_depot_node[v]
        dep_code = nodes_meta[dep_node].get("depot_code", depot_codes[dep_node] if dep_node < len(depot_codes) else "")
        prev_time = solution.Value(time_dim.CumulVar(index))
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            meta = nodes_meta[node]
            t = solution.Value(time_dim.CumulVar(index))
            wc = solution.Value(w_dim.CumulVar(index))
            st = solution.Value(s_dim.CumulVar(index))
            stop_rows.append({
                "vehicle_id": v,
                "depot_code": dep_code,
                "sequence": seq,
                "node_index": node,
                "node_type": meta["node_type"],
                "passenger": meta.get("passenger"),
                "request_idx": meta.get("request_idx"),
                "arrival_cumul_min": t,
                "wheelchair_load": wc,
                "seat_load": st,
            })
            index = solution.Value(routing.NextVar(index))
            seq += 1
        # end depot
        node = manager.IndexToNode(index)
        t = solution.Value(time_dim.CumulVar(index))
        stop_rows.append({
            "vehicle_id": v,
            "depot_code": dep_code,
            "sequence": seq,
            "node_index": node,
            "node_type": "depot_end",
            "passenger": None,
            "request_idx": None,
            "arrival_cumul_min": t,
            "wheelchair_load": solution.Value(w_dim.CumulVar(index)),
            "seat_load": solution.Value(s_dim.CumulVar(index)),
        })

    stops_df = pd.DataFrame(stop_rows)
    if stops_df.empty:
        return pd.DataFrame(), stops_df

    # 汇总每条车路线
    for v in stops_df["vehicle_id"].unique():
        sdf = stops_df[stops_df["vehicle_id"] == v]
        if len(sdf) <= 1:
            continue
        t0 = sdf["arrival_cumul_min"].iloc[0]
        t1 = sdf["arrival_cumul_min"].iloc[-1]
        pax_visits = sdf[sdf["node_type"] == "pickup"]
        route_rows.append({
            "vehicle_id": v,
            "depot_code": sdf["depot_code"].iloc[0],
            "num_stops": len(sdf),
            "num_pickups": len(pax_visits),
            "route_duration_min": int(t1 - t0),
        })
    routes_df = pd.DataFrame(route_rows)
    return routes_df, stops_df


def main() -> None:
    ap = argparse.ArgumentParser(description="Rehabus OR-Tools VRPTW + PDP")
    ap.add_argument("--passenger-csv", type=Path, default=ROOT / "passenger_input_clean_2.csv")
    ap.add_argument("--limit", type=int, default=None, help="仅优化前 N 条需求（调试强烈建议）")
    ap.add_argument("--time-limit", type=int, default=120, help="求解时间上限（秒）")
    ap.add_argument("--no-google", action="store_true", help="禁止 matrix_builder 内 Google 缓存叠加")
    ap.add_argument(
        "--google-depot-edges",
        action="store_true",
        help="对每条 depot→全节点弧调用 Google Matrix（需 API key；节点多时请求量大）",
    )
    ap.add_argument("--output-prefix", type=str, default="optimization_or_tools")
    args = ap.parse_args()

    parking_df = load_parking_data(ROOT)
    pax_df = load_passengers(args.passenger_csv, args.limit)
    if pax_df.empty:
        raise SystemExit("乘客数据为空，请检查 CSV 路径与字段")

    nodes_meta, pickup_map, drop_map, depot_indices, depot_codes = build_nodes_and_meta(parking_df, pax_df)
    nodes_df = meta_to_dataframe(nodes_meta)
    logger.info(
        "节点: depots=%d, 请求=%d, 总节点=%d, 车辆槽位=%d",
        len(depot_indices),
        len(pax_df),
        len(nodes_meta),
        int(parking_df["max_vehicles"].sum()),
    )

    use_google = not args.no_google
    time_mat = build_time_matrix(nodes_df, use_google=use_google)
    if args.google_depot_edges:
        time_mat = refine_matrix_depot_edges_google(
            time_mat.copy(), nodes_meta, depot_indices, batch=25
        )

    vehicle_slots = assign_vehicles_to_depots(parking_df)
    manager, routing, sol = solve(
        time_mat,
        nodes_meta,
        pax_df,
        pickup_map,
        drop_map,
        vehicle_slots,
        args.time_limit,
    )

    if not sol:
        logger.error("未找到可行解（可尝试增大 --time-limit、减小 --limit 或放宽约束）")
        sys.exit(2)

    routes_df, stops_df = solution_to_dataframes(
        manager, routing, sol, nodes_meta, vehicle_slots, depot_codes
    )
    used = routes_df[routes_df["num_pickups"] > 0]["vehicle_id"].nunique() if not routes_df.empty else 0
    logger.info("使用车辆数（有载客）: %s / %d", used, len(vehicle_slots))

    out_r = ROOT / f"{args.output_prefix}_routes.csv"
    out_s = ROOT / f"{args.output_prefix}_stops.csv"
    routes_df.to_csv(out_r, index=False)
    stops_df.to_csv(out_s, index=False)
    logger.info("已写入 %s 与 %s", out_r, out_s)
    print("OK:", out_r, out_s)


if __name__ == "__main__":
    main()
