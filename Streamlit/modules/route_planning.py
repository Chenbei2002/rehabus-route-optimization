"""Page 3 – 路线规划: optimization results viewer."""

from __future__ import annotations

from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from modules.old_data_preview import render_route_timeline
from utils.formatters import metric_card, page_header, section_start, section_end
from utils.styles import GREEN_SEQUENCE, apply_chart_style

APP_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = APP_DIR.parent

RESULT_FILENAMES = {
    "summary": "summary_results.csv",
    "routes": "optimized_routes.csv",
    "route_passengers": "optimized_route_passengers.csv",
    "vehicles": "vehicle_dispatch.csv",
    "vehicle_timeline": "vehicle_timeline.csv",
}

SCENARIO_LABELS = {
    "general": "General Optimization",
    "purpose_based": "Purpose-based Optimization（學習和工作最優）",
}


def render_route_planning(
    filtered_df: pd.DataFrame,
    full_df: pd.DataFrame,
    parking_df: pd.DataFrame,
) -> None:
    st.markdown(
        page_header("路線規劃", "優化結果展示頁面：方案總覽、路線詳情與車輛派遣結果"),
        unsafe_allow_html=True,
    )

    passenger_df = filtered_df if not filtered_df.empty else full_df
    scenario_key, scenario_title = render_plan_selector()
    result_bundle = load_result_bundle(passenger_df, parking_df, scenario_key)

    render_optimization_summary(result_bundle["summary"], scenario_title)
    st.divider()
    render_route_table(result_bundle["routes"])
    st.divider()
    render_route_detail(result_bundle["routes"], result_bundle["route_passengers"], parking_df)
    st.divider()
    render_vehicle_dispatch(result_bundle["vehicles"], result_bundle["vehicle_timeline"])


def render_plan_selector() -> tuple[str, str]:
    st.markdown(
        section_start("結果模式選擇", "先選擇優化方案類型，再查看當前方案結果"),
        unsafe_allow_html=True,
    )
    mode = st.radio(
        "優化方案類型",
        ["General Optimization", "Purpose-based Optimization"],
        horizontal=True,
        key="optimization_result_mode",
    )
    scenario_key = "general"
    scenario_title = SCENARIO_LABELS[scenario_key]
    if mode == "Purpose-based Optimization":
        st.info("當前 Purpose-based Optimization 採用固定優先級：學習和工作最優。")
        scenario_key = "purpose_based"
        scenario_title = SCENARIO_LABELS[scenario_key]
    st.markdown(section_end(), unsafe_allow_html=True)
    return scenario_key, scenario_title


def load_result_bundle(
    passenger_df: pd.DataFrame,
    parking_df: pd.DataFrame,
    scenario_key: str,
) -> dict[str, pd.DataFrame]:
    csv_bundle = _load_result_csv_bundle(scenario_key)
    if all(df is not None for df in csv_bundle.values()):
        routes_df = _standardize_routes_df(csv_bundle["routes"])
        route_passengers_df = _standardize_route_passengers_df(csv_bundle["route_passengers"])
        vehicle_df = _standardize_vehicle_dispatch_df(csv_bundle["vehicles"])
        vehicle_timeline_df = _standardize_vehicle_timeline_df(csv_bundle["vehicle_timeline"])
        summary_df = _standardize_summary_df(csv_bundle["summary"])
        if summary_df.empty:
            summary_df = _build_summary_df(routes_df, vehicle_df, scenario_key)
        return {
            "summary": summary_df,
            "routes": routes_df,
            "route_passengers": route_passengers_df,
            "vehicles": vehicle_df,
            "vehicle_timeline": vehicle_timeline_df,
        }

    return _generate_demo_bundle(passenger_df, parking_df, scenario_key)


def render_optimization_summary(summary_df: pd.DataFrame, scenario_title: str) -> None:
    st.markdown(
        section_start("當前方案總覽", f"當前查看：{scenario_title}"),
        unsafe_allow_html=True,
    )
    if summary_df.empty:
        st.info("當前沒有可展示的優化結果總覽。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    row = summary_df.iloc[0]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(metric_card(int(row["total_routes"]), "總路線數"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card(int(row["total_passengers"]), "總服務乘客數"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card(int(row["used_vehicles"]), "使用車輛數"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card(f"{row['avg_utilization']:.0f}%", "平均利用率"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card(f"{row['avg_trip_duration']:.1f} min", "平均行程時長"), unsafe_allow_html=True)
    with c6:
        st.markdown(metric_card(f"{row['total_service_duration']:.0f} min", "總服務時長"), unsafe_allow_html=True)
    st.markdown(section_end(), unsafe_allow_html=True)


def render_route_table(routes_df: pd.DataFrame) -> None:
    st.markdown(section_start("路線結果總表"), unsafe_allow_html=True)
    if routes_df.empty:
        st.info("當前資料不足以展示路線結果總表。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    st.dataframe(
        routes_df[
            [
                "route_id",
                "depot",
                "dominant_purpose",
                "passenger_count",
                "wheelchair_users",
                "seated_users",
                "trip_duration_minutes",
                "utilization_pct",
                "status",
            ]
        ],
        use_container_width=True,
        height=360,
        column_config={
            "route_id": "route_id",
            "depot": "depot",
            "dominant_purpose": "dominant_purpose",
            "passenger_count": "passenger_count",
            "wheelchair_users": "wheelchair_users",
            "seated_users": "seated_users",
            "trip_duration_minutes": st.column_config.NumberColumn("trip_duration_minutes", format="%.0f"),
            "utilization_pct": "utilization",
            "status": "status",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)


def render_route_detail(
    routes_df: pd.DataFrame,
    route_passengers_df: pd.DataFrame,
    parking_df: pd.DataFrame,
) -> None:
    st.markdown(section_start("單條路線詳情"), unsafe_allow_html=True)
    if routes_df.empty or route_passengers_df.empty:
        st.info("當前資料不足以展示單條路線詳情。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    route_options = routes_df["route_id"].astype(str).tolist()
    selected_route = st.selectbox("選擇 route_id", route_options, key="route_result_detail_id")
    route_row = routes_df[routes_df["route_id"].astype(str) == str(selected_route)].iloc[0]
    detail_df = route_passengers_df[route_passengers_df["route_id"].astype(str) == str(selected_route)].copy()
    detail_df = detail_df.sort_values("board_time_minutes", na_position="last")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("depot", route_row.get("depot", "-"))
    with m2:
        st.metric("dominant_purpose", route_row.get("dominant_purpose", "-"))
    with m3:
        st.metric("passenger_count", int(route_row.get("passenger_count", 0)))
    with m4:
        st.metric("utilization", route_row.get("utilization_pct", "-"))

    left, right = st.columns([1, 1])
    with left:
        st.markdown("### 乘客明細表")
        detail_cols = [
            c
            for c in [
                "passenger",
                "passenger_type",
                "purpose",
                "board_stop",
                "board_time_str",
                "alight_stop",
                "alight_time_str",
                "trip_duration_minutes_est",
            ]
            if c in detail_df.columns
        ]
        st.dataframe(
            detail_df[detail_cols],
            use_container_width=True,
            height=320,
        )
    with right:
        st.markdown("### 路線地圖")
        _render_selected_route_map(detail_df, route_row, parking_df)

    render_route_timeline(
        route_df=detail_df,
        passenger_col="passenger",
        board_time_min_col="board_time_minutes",
        alight_time_min_col="alight_time_minutes",
        board_stop_col="board_stop",
        alight_stop_col="alight_stop",
        passenger_type_col="passenger_type",
        wheelchair_col="is_wheelchair",
    )
    st.markdown(section_end(), unsafe_allow_html=True)


def render_vehicle_dispatch(vehicle_df: pd.DataFrame, vehicle_timeline_df: pd.DataFrame) -> None:
    st.markdown(section_start("車輛派遣結果"), unsafe_allow_html=True)
    if vehicle_df.empty:
        st.info("當前資料不足以展示車輛派遣結果。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    vehicle_cols = [
        c
        for c in [
            "vehicle_id",
            "depot",
            "assigned_routes",
            "route_count",
            "first_departure_str",
            "last_return_str",
            "total_service_minutes",
            "status",
        ]
        if c in vehicle_df.columns
    ]
    st.dataframe(
        vehicle_df[vehicle_cols],
        use_container_width=True,
        height=260,
        column_config={
            "vehicle_id": "vehicle_id",
            "depot": "depot",
            "assigned_routes": "assigned_routes",
            "route_count": "route_count",
            "first_departure_str": "first_departure",
            "last_return_str": "last_return",
            "total_service_minutes": st.column_config.NumberColumn("total_service_minutes", format="%.0f"),
            "status": "status",
        },
    )

    render_vehicle_timeline(vehicle_df, vehicle_timeline_df)
    st.markdown(section_end(), unsafe_allow_html=True)


def render_vehicle_timeline(vehicle_df: pd.DataFrame, vehicle_timeline_df: pd.DataFrame) -> None:
    st.markdown("### 車輛調度時間軸 / 甘特圖")
    if vehicle_timeline_df.empty:
        st.info("當前資料不足以展示車輛時間軸。")
        return

    vehicle_options = vehicle_df["vehicle_id"].astype(str).tolist()
    selected_vehicle = st.selectbox("選擇 vehicle_id", vehicle_options, key="vehicle_dispatch_detail_id")
    timeline_df = vehicle_timeline_df[vehicle_timeline_df["vehicle_id"].astype(str) == str(selected_vehicle)].copy()
    if timeline_df.empty:
        st.info("當前車輛沒有可展示的調度記錄。")
        return

    timeline_df["start_time"] = timeline_df["start_minutes"].apply(_minutes_to_datetime)
    timeline_df["end_time"] = timeline_df["end_minutes"].apply(_minutes_to_datetime)
    timeline_df["time_range"] = timeline_df.apply(
        lambda row: f"{_format_minutes(row['start_minutes'])} - {_format_minutes(row['end_minutes'])}",
        axis=1,
    )
    if "activity_label" not in timeline_df.columns:
        timeline_df["activity_label"] = timeline_df.get("route_id", "Route service")
    if "event_type" not in timeline_df.columns:
        timeline_df["event_type"] = "Route service"
    if "detail" not in timeline_df.columns:
        timeline_df["detail"] = timeline_df["activity_label"]
    if "display_lane" not in timeline_df.columns:
        timeline_df["display_lane"] = timeline_df["activity_label"]

    lane_order = timeline_df.sort_values("start_minutes")["display_lane"].astype(str).tolist()
    fig = px.timeline(
        timeline_df,
        x_start="start_time",
        x_end="end_time",
        y="display_lane",
        color="event_type",
        hover_data={
            "activity_label": True,
            "route_id": True,
            "depot": True,
            "passenger_count": True,
            "dominant_purpose": True,
            "detail": True,
            "time_range": True,
            "start_minutes": False,
            "end_minutes": False,
            "display_lane": False,
        },
        color_discrete_map={
            "Departure prep": "#95D5B2",
            "Fueling": "#E9A820",
            "Drive to first stop": "#74C69D",
            "Route service": "#2D6A4F",
            "Return to depot": "#40916C",
            "Standby": "#B7E4C7",
        },
    )
    apply_chart_style(fig, height=max(340, 100 + len(lane_order) * 56), xaxis_title="時間", yaxis_title="調度步驟")
    fig.update_xaxes(tickformat="%H:%M")
    fig.update_yaxes(categoryorder="array", categoryarray=lane_order, autorange="reversed")
    fig.update_traces(
        marker_line_color="rgba(0,0,0,0.12)",
        marker_line_width=1,
        hovertemplate=(
            "步驟: %{customdata[0]}<br>"
            "路線: %{customdata[1]}<br>"
            "Depot: %{customdata[2]}<br>"
            "乘客數: %{customdata[3]}<br>"
            "主要用途: %{customdata[4]}<br>"
            "說明: %{customdata[5]}<br>"
            "時間: %{customdata[6]}<extra></extra>"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("說明：當前車輛時間軸優先讀取真實 CSV；若缺失，則自動生成包含發車、加油、前往首站、執行路線、返回 Depot 的 demo 調度流程。")


def _load_result_csv_bundle(scenario_key: str) -> dict[str, pd.DataFrame | None]:
    return {
        name: _load_result_csv(filename, scenario_key)
        for name, filename in RESULT_FILENAMES.items()
    }


def _load_result_csv(filename: str, scenario_key: str) -> pd.DataFrame | None:
    for scenario_name in _scenario_aliases(scenario_key):
        candidates = [
            REPO_DIR / "output_data" / "optimization" / scenario_name / filename,
            REPO_DIR / "output_data" / scenario_name / filename,
            APP_DIR / "data" / scenario_name / filename,
        ]
        for path in candidates:
            if path.exists():
                df = pd.read_csv(path)
                if "scenario_key" in df.columns:
                    filtered = df[df["scenario_key"].astype(str) == scenario_name].copy()
                    return filtered if not filtered.empty else pd.DataFrame()
                return df
    fallback_candidates = [
        REPO_DIR / "output_data" / filename,
        APP_DIR / "data" / filename,
        REPO_DIR / filename,
    ]
    for path in fallback_candidates:
        if path.exists():
            df = pd.read_csv(path)
            if "scenario_key" in df.columns:
                aliases = _scenario_aliases(scenario_key)
                filtered = df[df["scenario_key"].astype(str).isin(aliases)].copy()
                return filtered if not filtered.empty else pd.DataFrame()
            return df
    return None


@st.cache_data(show_spinner=False)
def _generate_demo_bundle(
    passenger_df: pd.DataFrame,
    parking_df: pd.DataFrame,
    scenario_key: str,
) -> dict[str, pd.DataFrame]:
    rng = np.random.RandomState(_scenario_seed(scenario_key))
    base_df = _prepare_demo_passengers(passenger_df, rng)
    depots = _available_depots(parking_df)

    if base_df.empty:
        base_df = _synthetic_passengers(depots, rng)

    chunks = _chunk_passengers_into_routes(base_df, scenario_key)
    routes_rows: list[dict] = []
    passenger_rows: list[dict] = []
    vehicle_dispatch_rows: list[dict] = []
    vehicle_timeline_rows: list[dict] = []

    prefix = scenario_key.replace("_priority", "").replace("general", "gen").upper()[:3]
    for idx, chunk in enumerate(chunks, start=1):
        route_id = f"{prefix}-R{idx:03d}"
        vehicle_id = f"VH-{prefix}-{idx:03d}"
        depot = depots[(idx - 1) % len(depots)]

        chunk_df = pd.DataFrame(chunk).copy()
        route_start = int(chunk_df["board_time_minutes"].min())
        route_end = int(chunk_df["alight_time_minutes"].max())
        trip_duration = max(route_end - route_start, 20)
        wheelchair_users = int(chunk_df["is_wheelchair"].sum())
        seated_users = int(chunk_df["is_non_wheelchair"].sum())
        passenger_count = int(chunk_df["passenger"].nunique())
        dominant_purpose = _dominant_value(chunk_df["purpose"], default="Mixed")
        utilization_ratio = max(wheelchair_users / 5, seated_users / 10, passenger_count / 15)
        status = _build_status(utilization_ratio)

        routes_rows.append(
            {
                "scenario_key": scenario_key,
                "route_id": route_id,
                "vehicle_id": vehicle_id,
                "depot": depot,
                "dominant_purpose": dominant_purpose,
                "passenger_count": passenger_count,
                "wheelchair_users": wheelchair_users,
                "seated_users": seated_users,
                "trip_duration_minutes": trip_duration,
                "route_start_minutes": route_start,
                "route_end_minutes": route_end,
                "utilization": utilization_ratio,
                "utilization_pct_value": utilization_ratio * 100,
                "utilization_pct": f"{utilization_ratio:.0%}",
                "status": status,
            }
        )

        chunk_df["scenario_key"] = scenario_key
        chunk_df["route_id"] = route_id
        chunk_df["vehicle_id"] = vehicle_id
        chunk_df["depot"] = depot
        chunk_df["dominant_purpose"] = dominant_purpose
        passenger_rows.extend(chunk_df.to_dict("records"))

        fueling_start = max(route_start - int(rng.randint(35, 51)), 330)
        fueling_end = fueling_start + 15
        drive_to_first_minutes = int(rng.randint(8, 21))
        depart_depot_start = fueling_end
        depart_depot_end = depart_depot_start + drive_to_first_minutes
        route_service_start = min(max(depart_depot_end, route_start - int(rng.randint(0, 6))), route_start)
        return_to_depot_minutes = int(rng.randint(10, 26))
        return_end = route_end + return_to_depot_minutes
        standby_end = return_end + int(rng.randint(15, 46))

        vehicle_dispatch_rows.append(
            {
                "scenario_key": scenario_key,
                "vehicle_id": vehicle_id,
                "depot": depot,
                "assigned_routes": route_id,
                "route_count": 1,
                "first_departure_minutes": fueling_start,
                "last_return_minutes": return_end,
                "first_departure_str": _format_minutes(fueling_start),
                "last_return_str": _format_minutes(return_end),
                "total_service_minutes": return_end - fueling_start,
                "status": status,
            }
        )
        vehicle_timeline_rows.extend(
            [
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Departure prep",
                    "activity_label": "從 Depot 出發準備",
                    "display_lane": "1. 出發準備",
                    "detail": f"{depot} 車輛簽到、檢查清單、準備離場",
                    "start_minutes": fueling_start - 10,
                    "end_minutes": fueling_start,
                    "status": status,
                },
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Fueling",
                    "activity_label": "加油 / 補給",
                    "display_lane": "2. 加油 / 補給",
                    "detail": f"在 {depot} 完成加油與物資補給（15 分鐘）",
                    "start_minutes": fueling_start,
                    "end_minutes": fueling_end,
                    "status": status,
                },
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Drive to first stop",
                    "activity_label": "前往第一個停車點",
                    "display_lane": "3. 前往首站",
                    "detail": f"從 {depot} 行駛 {drive_to_first_minutes} 分鐘到達首個上車點",
                    "start_minutes": depart_depot_start,
                    "end_minutes": depart_depot_end,
                    "status": status,
                },
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Route service",
                    "activity_label": f"執行路線 {route_id}",
                    "display_lane": "4. 執行路線",
                    "detail": f"服務 {passenger_count} 名乘客，主要用途：{dominant_purpose}",
                    "start_minutes": route_service_start,
                    "end_minutes": route_end,
                    "status": status,
                },
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Return to depot",
                    "activity_label": "返回 Depot",
                    "display_lane": "5. 返回 Depot",
                    "detail": f"完成路線後返回 {depot}，預計 {return_to_depot_minutes} 分鐘",
                    "start_minutes": route_end,
                    "end_minutes": return_end,
                    "status": status,
                },
                {
                    "scenario_key": scenario_key,
                    "vehicle_id": vehicle_id,
                    "route_id": route_id,
                    "depot": depot,
                    "dominant_purpose": dominant_purpose,
                    "passenger_count": passenger_count,
                    "event_type": "Standby",
                    "activity_label": "回場待命",
                    "display_lane": "6. 回場待命",
                    "detail": f"返回 {depot} 後待命，準備下一班次",
                    "start_minutes": return_end,
                    "end_minutes": standby_end,
                    "status": status,
                },
            ]
        )

    routes_df = pd.DataFrame(routes_rows)
    route_passengers_df = pd.DataFrame(passenger_rows)
    vehicles_df = pd.DataFrame(vehicle_dispatch_rows)
    vehicle_timeline_df = pd.DataFrame(vehicle_timeline_rows)
    summary_df = _build_summary_df(routes_df, vehicles_df, scenario_key)

    return {
        "summary": summary_df,
        "routes": routes_df,
        "route_passengers": route_passengers_df,
        "vehicles": vehicles_df,
        "vehicle_timeline": vehicle_timeline_df,
    }


def _prepare_demo_passengers(passenger_df: pd.DataFrame, rng: np.random.RandomState) -> pd.DataFrame:
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame()

    required_cols = [
        "passenger",
        "purpose",
        "board_stop",
        "board_lat",
        "board_lng",
        "board_time_minutes",
        "alight_stop",
        "alight_lat",
        "alight_lng",
        "alight_time_minutes",
        "trip_duration_minutes_est",
        "is_wheelchair",
        "is_non_wheelchair",
    ]

    base = passenger_df.copy()
    for col in required_cols:
        if col not in base.columns:
            base[col] = pd.NA

    if "passenger_type" not in base.columns:
        base["passenger_type"] = np.where(base["is_wheelchair"].fillna(0).astype(int) == 1, "WC", "NWC")

    base = base.drop_duplicates("passenger")
    base["board_time_minutes"] = pd.to_numeric(base["board_time_minutes"], errors="coerce")
    base["alight_time_minutes"] = pd.to_numeric(base["alight_time_minutes"], errors="coerce")
    base["trip_duration_minutes_est"] = pd.to_numeric(base["trip_duration_minutes_est"], errors="coerce")
    base = base.dropna(subset=["board_time_minutes", "alight_time_minutes"])
    if base.empty:
        return pd.DataFrame()

    sample_size = min(max(40, len(base) // 3), len(base))
    base = base.sample(n=sample_size, random_state=rng.randint(1, 9999)).copy()
    base["purpose"] = base["purpose"].fillna("other").astype(str)
    base["board_time_minutes"] = base["board_time_minutes"].clip(lower=360, upper=1080)
    base["alight_time_minutes"] = base[["alight_time_minutes", "board_time_minutes"]].max(axis=1)
    base["alight_time_minutes"] = np.maximum(
        base["alight_time_minutes"].fillna(base["board_time_minutes"] + 40),
        base["board_time_minutes"] + 20,
    )
    base["board_time_str"] = base["board_time_minutes"].apply(_format_minutes)
    base["alight_time_str"] = base["alight_time_minutes"].apply(_format_minutes)
    base["is_wheelchair"] = pd.to_numeric(base["is_wheelchair"], errors="coerce").fillna(0).astype(int)
    if "is_non_wheelchair" in base.columns:
        base["is_non_wheelchair"] = pd.to_numeric(base["is_non_wheelchair"], errors="coerce").fillna(0).astype(int)
    else:
        base["is_non_wheelchair"] = 1 - base["is_wheelchair"]
    return base


def _synthetic_passengers(depots: list[str], rng: np.random.RandomState) -> pd.DataFrame:
    purposes = ["work", "study", "training", "other"]
    rows = []
    for i in range(48):
        board_time = int(rng.randint(390, 630))
        duration = int(rng.randint(30, 95))
        wc = int(rng.rand() < 0.2)
        rows.append(
            {
                "passenger": f"Demo Passenger {i+1}",
                "passenger_type": "WC" if wc else "NWC",
                "purpose": str(rng.choice(purposes)),
                "board_stop": f"Board Stop {i%12 + 1}",
                "board_lat": 22.25 + rng.rand() * 0.08,
                "board_lng": 114.12 + rng.rand() * 0.12,
                "board_time_minutes": board_time,
                "board_time_str": _format_minutes(board_time),
                "alight_stop": f"Alight Stop {i%10 + 1}",
                "alight_lat": 22.25 + rng.rand() * 0.08,
                "alight_lng": 114.12 + rng.rand() * 0.12,
                "alight_time_minutes": board_time + duration,
                "alight_time_str": _format_minutes(board_time + duration),
                "trip_duration_minutes_est": duration,
                "is_wheelchair": wc,
                "is_non_wheelchair": 0 if wc else 1,
                "existing_route": str(rng.choice(depots)),
            }
        )
    return pd.DataFrame(rows)


def _chunk_passengers_into_routes(base_df: pd.DataFrame, scenario_key: str) -> list[list[dict]]:
    ordered = base_df.copy()
    ordered["priority_rank"] = ordered["purpose"].apply(lambda x: _purpose_priority_rank(str(x), scenario_key))
    ordered = ordered.sort_values(["priority_rank", "board_time_minutes", "purpose"]).reset_index(drop=True)

    chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    wc_count = 0
    seated_count = 0
    for row in ordered.to_dict("records"):
        wc = int(row.get("is_wheelchair", 0))
        seated = int(row.get("is_non_wheelchair", 1 if not wc else 0))
        if current_chunk and (wc_count + wc > 5 or seated_count + seated > 10 or len(current_chunk) >= 12):
            chunks.append(current_chunk)
            current_chunk = []
            wc_count = 0
            seated_count = 0

        current_chunk.append(row)
        wc_count += wc
        seated_count += seated

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _purpose_priority_rank(purpose: str, scenario_key: str) -> tuple[int, float]:
    priority_map = {
        "general": ["work", "study", "training", "other"],
        "purpose_based": ["study", "work", "training", "other"],
    }
    order = priority_map.get(scenario_key, priority_map["general"])
    purpose_lower = purpose.lower()
    for idx, key in enumerate(order):
        if key in purpose_lower:
            return (idx, 0)
    return (len(order), 0)


def _build_summary_df(routes_df: pd.DataFrame, vehicles_df: pd.DataFrame, scenario_key: str) -> pd.DataFrame:
    if routes_df.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "scenario_key": scenario_key,
                "total_routes": int(routes_df["route_id"].nunique()),
                "total_passengers": int(routes_df["passenger_count"].sum()),
                "used_vehicles": int(vehicles_df["vehicle_id"].nunique()) if not vehicles_df.empty else int(routes_df["route_id"].nunique()),
                "avg_utilization": float(routes_df["utilization_pct_value"].mean()),
                "avg_trip_duration": float(routes_df["trip_duration_minutes"].mean()),
                "total_service_duration": float(routes_df["trip_duration_minutes"].sum()),
            }
        ]
    )


def _standardize_summary_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename_map = {
        "total_service_passengers": "total_passengers",
        "vehicles_used": "used_vehicles",
        "avg_trip_duration_minutes": "avg_trip_duration",
    }
    standardized = df.rename(columns=rename_map).copy()
    required = [
        "total_routes",
        "total_passengers",
        "used_vehicles",
        "avg_utilization",
        "avg_trip_duration",
        "total_service_duration",
    ]
    for col in required:
        if col not in standardized.columns:
            standardized[col] = 0
    return standardized[required + [c for c in standardized.columns if c not in required]]


def _standardize_routes_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename_map = {
        "wheelchair_count": "wheelchair_users",
        "seated_count": "seated_users",
        "estimated_duration": "trip_duration_minutes",
    }
    standardized = df.rename(columns=rename_map).copy()
    if "utilization" in standardized.columns and standardized["utilization"].max() <= 1.5:
        standardized["utilization_pct_value"] = standardized["utilization"] * 100
        standardized["utilization_pct"] = standardized["utilization"].map(lambda x: f"{x:.0%}")
    else:
        standardized["utilization_pct_value"] = pd.to_numeric(standardized.get("utilization", 0), errors="coerce").fillna(0)
        standardized["utilization_pct"] = standardized["utilization_pct_value"].map(lambda x: f"{x:.0f}%")
        standardized["utilization"] = standardized["utilization_pct_value"] / 100

    if "status" not in standardized.columns:
        standardized["status"] = standardized["utilization"].apply(_build_status)
    if "dominant_purpose" not in standardized.columns:
        standardized["dominant_purpose"] = standardized.get("scenario", "Mixed")
    if "depot" not in standardized.columns:
        standardized["depot"] = "-"
    return standardized


def _standardize_route_passengers_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    standardized = df.copy()
    if "board_time_str" not in standardized.columns and "board_time_minutes" in standardized.columns:
        standardized["board_time_str"] = pd.to_numeric(standardized["board_time_minutes"], errors="coerce").apply(_format_minutes)
    if "alight_time_str" not in standardized.columns and "alight_time_minutes" in standardized.columns:
        standardized["alight_time_str"] = pd.to_numeric(standardized["alight_time_minutes"], errors="coerce").apply(_format_minutes)
    if "passenger_type" not in standardized.columns and "is_wheelchair" in standardized.columns:
        standardized["passenger_type"] = np.where(
            pd.to_numeric(standardized["is_wheelchair"], errors="coerce").fillna(0).astype(int) == 1,
            "WC",
            "NWC",
        )
    return standardized


def _standardize_vehicle_dispatch_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    standardized = df.copy()
    for col in ("first_departure_minutes", "last_return_minutes", "total_service_minutes"):
        if col not in standardized.columns:
            standardized[col] = pd.NA
    if "first_departure_str" not in standardized.columns and "first_departure_minutes" in standardized.columns:
        standardized["first_departure_str"] = pd.to_numeric(standardized["first_departure_minutes"], errors="coerce").apply(_format_minutes)
    if "last_return_str" not in standardized.columns and "last_return_minutes" in standardized.columns:
        standardized["last_return_str"] = pd.to_numeric(standardized["last_return_minutes"], errors="coerce").apply(_format_minutes)
    return standardized


def _standardize_vehicle_timeline_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    standardized = df.copy()
    if "event_type" not in standardized.columns:
        standardized["event_type"] = "Route service"
    if "activity_label" not in standardized.columns:
        standardized["activity_label"] = standardized.get("route_id", "Route service")
    if "display_lane" not in standardized.columns:
        standardized["display_lane"] = standardized["activity_label"]
    if "detail" not in standardized.columns:
        standardized["detail"] = standardized["activity_label"]
    for col in ("route_id", "depot", "dominant_purpose", "passenger_count", "status"):
        if col not in standardized.columns:
            standardized[col] = "-"
    return standardized


def _render_selected_route_map(route_df: pd.DataFrame, route_row: pd.Series, parking_df: pd.DataFrame) -> None:
    if route_df.empty or route_df[["board_lat", "board_lng"]].dropna().empty:
        st.info("當前路線缺少座標資料，無法繪製地圖。")
        return

    map_df = route_df.dropna(subset=["board_lat", "board_lng"]).copy()
    map_df["board_lat"] = pd.to_numeric(map_df["board_lat"], errors="coerce")
    map_df["board_lng"] = pd.to_numeric(map_df["board_lng"], errors="coerce")
    map_df["alight_lat"] = pd.to_numeric(map_df["alight_lat"], errors="coerce")
    map_df["alight_lng"] = pd.to_numeric(map_df["alight_lng"], errors="coerce")
    map_df = map_df.dropna(subset=["board_lat", "board_lng"])
    if map_df.empty:
        st.info("當前路線座標欄位無法解析為數值。")
        return

    m = folium.Map(
        location=[map_df["board_lat"].mean(), map_df["board_lng"].mean()],
        zoom_start=12,
        tiles="cartodbpositron",
    )

    depot_code = route_row.get("depot")
    if depot_code is not None and not parking_df.empty and "depot_code" in parking_df.columns:
        depot_match = parking_df[parking_df["depot_code"].astype(str) == str(depot_code)]
        if not depot_match.empty and depot_match[["lat", "lon"]].dropna().shape[0] > 0:
            depot_row = depot_match.iloc[0]
            folium.Marker(
                [depot_row["lat"], depot_row["lon"]],
                tooltip=f"Depot: {depot_row.get('depot_code', '-')}",
                popup=f"<b>{depot_row.get('depot_name', '-')}</b>",
                icon=folium.Icon(color="darkgreen", icon="home", prefix="fa"),
            ).add_to(m)

    coords: list[tuple[float, float]] = []
    for _, row in map_df.iterrows():
        coords.append((row["board_lat"], row["board_lng"]))
        folium.CircleMarker(
            [row["board_lat"], row["board_lng"]],
            radius=5,
            color="#2D6A4F",
            fill=True,
            fill_color="#2D6A4F",
            fill_opacity=0.8,
            tooltip=f"上車: {row.get('passenger', '-')}",
        ).add_to(m)
        if pd.notna(row.get("alight_lat")) and pd.notna(row.get("alight_lng")):
            folium.CircleMarker(
                [row["alight_lat"], row["alight_lng"]],
                radius=4,
                color="#40916C",
                fill=True,
                fill_color="#74C69D",
                fill_opacity=0.5,
                tooltip=f"下車: {row.get('passenger', '-')}",
            ).add_to(m)

    if len(coords) >= 2:
        folium.PolyLine(coords, color="#2D6A4F", weight=3, opacity=0.75).add_to(m)

    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    st_folium(m, use_container_width=True, height=360, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)


def _dominant_value(series: pd.Series, default: str = "-") -> str:
    cleaned = series.dropna().astype(str)
    if cleaned.empty:
        return default
    return cleaned.mode().iloc[0]


def _available_depots(parking_df: pd.DataFrame) -> list[str]:
    if parking_df is None or parking_df.empty or "depot_code" not in parking_df.columns:
        return ["KLB1", "SKW", "TM1"]
    depots = parking_df["depot_code"].dropna().astype(str).unique().tolist()
    return depots or ["KLB1", "SKW", "TM1"]


def _scenario_seed(scenario_key: str) -> int:
    mapping = {
        "general": 42,
        "purpose_based": 202,
    }
    return mapping.get(scenario_key, 42)


def _scenario_aliases(scenario_key: str) -> list[str]:
    alias_map = {
        "general": ["general"],
        "purpose_based": ["purpose_based", "study_priority", "work_priority", "training_priority", "other_priority"],
    }
    return alias_map.get(scenario_key, [scenario_key])


def _build_status(utilization_ratio: float) -> str:
    if pd.isna(utilization_ratio):
        return "Unknown"
    if utilization_ratio >= 0.95:
        return "Critical"
    if utilization_ratio >= 0.8:
        return "High"
    return "Normal"


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _minutes_to_datetime(minutes: float | int | None) -> pd.Timestamp:
    base = pd.Timestamp("2024-01-01 00:00:00")
    if pd.isna(minutes):
        minutes = 0
    return base + pd.to_timedelta(float(minutes), unit="m")


def _format_minutes(minutes: float | int | None) -> str:
    if pd.isna(minutes):
        return "-"
    total = int(float(minutes))
    hour = total // 60
    minute = total % 60
    return f"{hour:02d}:{minute:02d}"
