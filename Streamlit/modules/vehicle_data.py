"""Page 2 – 车辆数据: vehicle resource and capacity monitoring."""

from __future__ import annotations

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from utils.formatters import metric_card, page_header, section_start, section_end
from utils.styles import GREEN_SEQUENCE, apply_chart_style

WC_CAPACITY_PER_VEHICLE = 5
SEATED_CAPACITY_PER_VEHICLE = 10

FIELD_MAP = {
    "depot_code": ["depot_code", "Depot Code", "ABB.", "abb"],
    "depot_name": ["depot_name", "Depot Name", "depot"],
    "lat": ["lat", "Lat.", "latitude"],
    "lon": ["lon", "Long.", "lng", "longitude"],
    "max_vehicles": ["max_vehicles", "Max number of vehicle allocated", "max_vehicle_allocated"],
    "route_id": ["existing_route", "route_id", "route"],
    "passenger": ["passenger", "passenger_id"],
    "wheelchair": ["is_wheelchair"],
    "seated": ["is_non_wheelchair"],
    "board_time_minutes": ["board_time_minutes"],
    "alight_time_minutes": ["alight_time_minutes"],
    "trip_duration_minutes_est": ["trip_duration_minutes_est"],
}


def render_vehicle_data(parking_df: pd.DataFrame, passenger_df: pd.DataFrame | None = None) -> None:
    st.markdown(
        page_header("車輛資料", "車輛資源與容量監控：Depot 資源、容量約束與使用壓力分析"),
        unsafe_allow_html=True,
    )

    depot_df = normalize_vehicle_fields(parking_df)
    route_capacity_df = build_route_capacity_summary(passenger_df)

    if depot_df.empty:
        st.warning("當前缺少停車點資源資料，無法展示車輛頁面。")
        return

    render_vehicle_kpis(depot_df)
    st.divider()
    render_depot_distribution(depot_df)
    st.divider()
    render_capacity_constraints(route_capacity_df)
    st.divider()
    render_vehicle_pressure_analysis(passenger_df)


def normalize_vehicle_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    rename_map: dict[str, str] = {}
    for logical_name, candidates in FIELD_MAP.items():
        if logical_name in {"route_id", "passenger", "wheelchair", "seated", "board_time_minutes", "alight_time_minutes", "trip_duration_minutes_est"}:
            continue
        resolved = _resolve_column(normalized, candidates)
        if resolved:
            rename_map[resolved] = logical_name

    normalized = normalized.rename(columns=rename_map)

    required_cols = ["depot_code", "depot_name", "lat", "lon", "max_vehicles"]
    for col in required_cols:
        if col not in normalized.columns:
            normalized[col] = pd.NA

    for col in ("lat", "lon", "max_vehicles"):
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized["max_vehicles"] = normalized["max_vehicles"].fillna(0).astype(int)
    normalized["depot_code"] = normalized["depot_code"].fillna("-").astype(str)
    normalized["depot_name"] = normalized["depot_name"].fillna("-").astype(str)
    return normalized


def render_vehicle_kpis(df: pd.DataFrame) -> None:
    total_vehicles = int(df["max_vehicles"].sum())
    depot_count = int(df["depot_name"].nunique()) if "depot_name" in df.columns else len(df)
    avg_vehicles_per_depot = total_vehicles / depot_count if depot_count else 0
    max_vehicles = int(df["max_vehicles"].max()) if not df.empty else 0
    total_wc_capacity = total_vehicles * WC_CAPACITY_PER_VEHICLE
    total_seated_capacity = total_vehicles * SEATED_CAPACITY_PER_VEHICLE

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card(total_vehicles, "總車輛數"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card(total_wc_capacity, "總 WC 容量"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card(total_seated_capacity, "總 seated 容量"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card(f"{avg_vehicles_per_depot:.1f}", "平均每個 Depot 配車數"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card(max_vehicles, "最大 Depot 配車數"), unsafe_allow_html=True)

    st.caption(f"Depot 數量：{depot_count} | 平均單個 Depot 容量：{avg_vehicles_per_depot:.1f} 輛")


def render_depot_distribution(df: pd.DataFrame) -> None:
    top_left, top_right = st.columns([1, 1])
    with top_left:
        _render_depot_table(df)
    with top_right:
        _render_depot_map(df)

    bottom_left, bottom_right = st.columns([1, 1])
    with bottom_left:
        _render_capacity_ranking(df)
    with bottom_right:
        _render_capacity_distribution(df)


def render_capacity_constraints(route_capacity_df: pd.DataFrame) -> None:
    st.markdown(
        section_start("容量約束分析", "圍繞單車 WC=5、Seated=10 的固定業務約束，監控各路線容量使用情況"),
        unsafe_allow_html=True,
    )

    render_capacity_rule_card()

    if route_capacity_df.empty:
        st.info("當前資料不足以展示路線容量利用率分析。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    render_capacity_utilization_chart(route_capacity_df)
    render_capacity_warning_table(route_capacity_df)
    render_route_capacity_table(route_capacity_df)
    st.markdown(section_end(), unsafe_allow_html=True)


def render_capacity_rule_card() -> None:
    st.info(
        "單車容量規則：Wheelchair capacity = 5，Seated capacity = 10。"
        "容量約束以 journey 過程中任意時點 simultaneously onboard 為準。"
    )


def build_route_capacity_summary(passenger_df: pd.DataFrame | None) -> pd.DataFrame:
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame()

    route_col = _resolve_column(passenger_df, FIELD_MAP["route_id"])
    passenger_col = _resolve_column(passenger_df, FIELD_MAP["passenger"])
    wheelchair_col = _resolve_column(passenger_df, FIELD_MAP["wheelchair"])
    seated_col = _resolve_column(passenger_df, FIELD_MAP["seated"])
    duration_col = _resolve_column(passenger_df, FIELD_MAP["trip_duration_minutes_est"])
    board_time_col = _resolve_column(passenger_df, FIELD_MAP["board_time_minutes"])
    alight_time_col = _resolve_column(passenger_df, FIELD_MAP["alight_time_minutes"])

    if route_col is None or passenger_col is None:
        return pd.DataFrame()

    df = passenger_df.copy()
    grouped = df.groupby(route_col, dropna=False)

    summary = grouped.agg(
        total_passengers=(passenger_col, "nunique"),
    ).reset_index().rename(columns={route_col: "route_id"})

    if wheelchair_col:
        wheelchair_df = grouped[wheelchair_col].sum(min_count=1).fillna(0).reset_index(name="wheelchair_users")
        wheelchair_df = wheelchair_df.rename(columns={route_col: "route_id"})
        summary = summary.merge(wheelchair_df, on="route_id", how="left")
    else:
        summary["wheelchair_users"] = 0

    if seated_col:
        seated_df = grouped[seated_col].sum(min_count=1).fillna(0).reset_index(name="seated_users")
        seated_df = seated_df.rename(columns={route_col: "route_id"})
        summary = summary.merge(seated_df, on="route_id", how="left")
    else:
        summary["seated_users"] = summary["total_passengers"] - summary["wheelchair_users"]

    if duration_col:
        duration_df = grouped[duration_col].mean().reset_index(name="avg_trip_duration_minutes")
        duration_df = duration_df.rename(columns={route_col: "route_id"})
        summary = summary.merge(duration_df, on="route_id", how="left")
    else:
        summary["avg_trip_duration_minutes"] = pd.NA

    if board_time_col:
        start_df = grouped[board_time_col].min().reset_index(name="route_start_minutes")
        start_df = start_df.rename(columns={route_col: "route_id"})
        summary = summary.merge(start_df, on="route_id", how="left")

    if alight_time_col:
        end_df = grouped[alight_time_col].max().reset_index(name="route_end_minutes")
        end_df = end_df.rename(columns={route_col: "route_id"})
        summary = summary.merge(end_df, on="route_id", how="left")

    summary["wheelchair_users"] = pd.to_numeric(summary["wheelchair_users"], errors="coerce").fillna(0)
    summary["seated_users"] = pd.to_numeric(summary["seated_users"], errors="coerce").fillna(0)
    summary["wc_utilization"] = summary["wheelchair_users"] / WC_CAPACITY_PER_VEHICLE
    summary["seated_utilization"] = summary["seated_users"] / SEATED_CAPACITY_PER_VEHICLE
    summary["warning_level"] = summary.apply(build_warning_level, axis=1)
    summary["warning_rank"] = summary["warning_level"].map({"Critical": 0, "High": 1, "Normal": 2}).fillna(3)
    summary["wc_utilization_pct_value"] = summary["wc_utilization"] * 100
    summary["seated_utilization_pct_value"] = summary["seated_utilization"] * 100
    summary["wc_utilization_pct"] = summary["wc_utilization"].map(lambda x: f"{x:.0%}")
    summary["seated_utilization_pct"] = summary["seated_utilization"].map(lambda x: f"{x:.0%}")
    return summary.sort_values(["warning_rank", "total_passengers"], ascending=[True, False])


def build_warning_level(row: pd.Series) -> str:
    max_util = max(float(row.get("wc_utilization", 0)), float(row.get("seated_utilization", 0)))
    if max_util >= 1:
        return "Critical"
    if max_util > 0.8:
        return "High"
    return "Normal"


def render_capacity_utilization_chart(route_capacity_df: pd.DataFrame) -> None:
    controls_left, controls_right = st.columns([2, 1])
    with controls_left:
        selected_metric = st.radio(
            "查看利用率指標",
            ["WC utilization", "Seated utilization", "Total passengers"],
            horizontal=True,
            key="vehicle_capacity_metric",
        )
    with controls_right:
        top_n = st.slider("Top N routes", min_value=5, max_value=30, value=12, key="vehicle_capacity_top_n")

    metric_map = {
        "WC utilization": ("wc_utilization", "WC 利用率", "wheelchair_users"),
        "Seated utilization": ("seated_utilization", "Seated 利用率", "seated_users"),
        "Total passengers": ("total_passengers", "總乘客數", "total_passengers"),
    }
    metric_col, y_label, hover_count_col = metric_map[selected_metric]

    chart_df = route_capacity_df.sort_values(metric_col, ascending=False).head(top_n).copy()
    fig = px.bar(
        chart_df,
        x="route_id",
        y=metric_col,
        color="warning_level",
        text=metric_col if metric_col == "total_passengers" else None,
        color_discrete_map={"Normal": GREEN_SEQUENCE[2], "High": "#E9A820", "Critical": "#D64045"},
        hover_data={
            "route_id": True,
            "wheelchair_users": True,
            "seated_users": True,
            "total_passengers": True,
            "wc_utilization": ":.0%",
            "seated_utilization": ":.0%",
            "warning_level": True,
        },
    )
    apply_chart_style(fig, height=380, xaxis_title="路線", yaxis_title=y_label, showlegend=True)
    fig.update_xaxes(tickangle=-45)
    if metric_col != "total_passengers":
        fig.update_yaxes(tickformat=".0%")
    else:
        fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)


def render_capacity_warning_table(route_capacity_df: pd.DataFrame) -> None:
    warning_df = route_capacity_df[
        (route_capacity_df["wc_utilization"] > 0.8) | (route_capacity_df["seated_utilization"] > 0.8)
    ].copy()

    st.markdown("### 容量預警路線表")
    if warning_df.empty:
        st.info("當前沒有超過 80% 容量閾值的路線。")
        return

    st.dataframe(
        warning_df[
            [
                "route_id",
                "wheelchair_users",
                "seated_users",
                "total_passengers",
                "warning_rank",
                "wc_utilization_pct_value",
                "seated_utilization_pct_value",
                "warning_level",
            ]
        ].sort_values(["warning_rank", "wc_utilization_pct_value", "seated_utilization_pct_value"], ascending=[True, False, False]),
        use_container_width=True,
        height=260,
        column_config={
            "route_id": "路線",
            "wheelchair_users": "輪椅人數",
            "seated_users": "座位人數",
            "total_passengers": "總人數",
            "warning_rank": None,
            "wc_utilization_pct_value": st.column_config.NumberColumn("WC 利用率", format="%.0f%%"),
            "seated_utilization_pct_value": st.column_config.NumberColumn("Seated 利用率", format="%.0f%%"),
            "warning_level": "預警等級",
        },
    )


def render_route_capacity_table(route_capacity_df: pd.DataFrame) -> None:
    st.markdown("### 路線容量與使用壓力表")
    table_df = route_capacity_df.copy()
    st.dataframe(
        table_df[
            [
                "route_id",
                "total_passengers",
                "wheelchair_users",
                "seated_users",
                "wc_utilization_pct",
                "seated_utilization_pct",
                "avg_trip_duration_minutes",
                "warning_level",
            ]
        ],
        use_container_width=True,
        height=320,
        column_config={
            "route_id": "路線",
            "total_passengers": "總人數",
            "wheelchair_users": "輪椅人數",
            "seated_users": "座位人數",
            "wc_utilization_pct": "WC 利用率",
            "seated_utilization_pct": "Seated 利用率",
            "avg_trip_duration_minutes": st.column_config.NumberColumn("平均行程時長(分鐘)", format="%.1f"),
            "warning_level": "狀態",
        },
    )


def render_vehicle_pressure_analysis(passenger_df: pd.DataFrame | None) -> None:
    st.markdown(
        section_start("車輛使用壓力分析", "觀察一天內路線出發、結束和行程時長的使用節奏"),
        unsafe_allow_html=True,
    )

    pressure_df = build_vehicle_pressure_summary(passenger_df)
    if pressure_df.empty:
        st.info("當前資料不足以展示車輛使用壓力分析。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    left, right = st.columns([2, 1])
    with left:
        selected_metric = st.radio(
            "查看壓力指標",
            ["路線出發時間", "路線結束時間", "行程時長"],
            horizontal=True,
            key="vehicle_pressure_metric",
        )
    with right:
        grain = st.selectbox("時間粒度", ["按小時", "按30分鐘"], index=0, key="vehicle_pressure_grain")

    grain_minutes = 60 if grain == "按小時" else 30

    if selected_metric == "行程時長":
        fig = px.histogram(
            pressure_df.dropna(subset=["avg_trip_duration_minutes"]),
            x="avg_trip_duration_minutes",
            nbins=20,
            color_discrete_sequence=[GREEN_SEQUENCE[3]],
        )
        apply_chart_style(fig, height=360, xaxis_title="平均行程時長（分鐘）", yaxis_title="路線數")
        st.plotly_chart(fig, use_container_width=True)
    else:
        time_col = "route_start_minutes" if selected_metric == "路線出發時間" else "route_end_minutes"
        hourly_df = _build_time_bucket_distribution(pressure_df, time_col, grain_minutes)
        if hourly_df.empty:
            st.info("當前資料不足以展示所選時間分佈。")
        else:
            fig = px.bar(
                hourly_df,
                x="bucket_label",
                y="count",
                text="count",
                color_discrete_sequence=[GREEN_SEQUENCE[1]],
            )
            apply_chart_style(fig, height=360, xaxis_title=selected_metric, yaxis_title="路線數")
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_xaxes(type="category")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown(section_end(), unsafe_allow_html=True)


def build_vehicle_pressure_summary(passenger_df: pd.DataFrame | None) -> pd.DataFrame:
    if passenger_df is None or passenger_df.empty:
        return pd.DataFrame()

    route_col = _resolve_column(passenger_df, FIELD_MAP["route_id"])
    board_time_col = _resolve_column(passenger_df, FIELD_MAP["board_time_minutes"])
    alight_time_col = _resolve_column(passenger_df, FIELD_MAP["alight_time_minutes"])
    duration_col = _resolve_column(passenger_df, FIELD_MAP["trip_duration_minutes_est"])

    if route_col is None:
        return pd.DataFrame()

    available_aggs: dict[str, tuple[str, str]] = {}
    if board_time_col:
        available_aggs["route_start_minutes"] = (board_time_col, "min")
    if alight_time_col:
        available_aggs["route_end_minutes"] = (alight_time_col, "max")
    if duration_col:
        available_aggs["avg_trip_duration_minutes"] = (duration_col, "mean")

    if not available_aggs:
        return pd.DataFrame()

    pressure_df = (
        passenger_df.groupby(route_col)
        .agg(**available_aggs)
        .reset_index()
        .rename(columns={route_col: "route_id"})
    )
    return pressure_df


def _render_depot_table(df: pd.DataFrame) -> None:
    st.markdown(section_start("停車點資訊表"), unsafe_allow_html=True)
    st.dataframe(
        df[["depot_code", "depot_name", "lat", "lon", "max_vehicles"]],
        use_container_width=True,
        height=460,
        column_config={
            "depot_code": "代碼",
            "depot_name": "停車點名稱",
            "lat": st.column_config.NumberColumn("緯度", format="%.6f"),
            "lon": st.column_config.NumberColumn("經度", format="%.6f"),
            "max_vehicles": "最大車輛數",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)


def _render_depot_map(df: pd.DataFrame) -> None:
    st.markdown(section_start("停車點地圖", "氣泡大小反映 Depot 可配置車輛數"), unsafe_allow_html=True)

    map_df = df.dropna(subset=["lat", "lon"])
    if map_df.empty:
        st.info("當前資料不足以展示停車點地圖。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    center_lat = map_df["lat"].mean()
    center_lon = map_df["lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="cartodbpositron")

    for _, row in map_df.iterrows():
        radius = max(5, int(row["max_vehicles"]) * 0.9)
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=radius,
            popup=folium.Popup(
                f"<b>{row['depot_name']}</b><br>代碼: {row['depot_code']}<br>最大車輛數: {row['max_vehicles']}",
                max_width=260,
            ),
            tooltip=f"{row['depot_name']} ({row['max_vehicles']}輛)",
            color="#2D6A4F",
            fill=True,
            fill_color="#40916C",
            fill_opacity=0.65,
        ).add_to(m)

    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    st_folium(m, use_container_width=True, height=450, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(section_end(), unsafe_allow_html=True)


def _render_capacity_ranking(df: pd.DataFrame) -> None:
    st.markdown(section_start("停車容量排序"), unsafe_allow_html=True)
    sorted_df = df.sort_values("max_vehicles", ascending=True)
    fig = px.bar(
        sorted_df,
        x="max_vehicles",
        y="depot_name",
        orientation="h",
        text="max_vehicles",
        color="max_vehicles",
        color_continuous_scale=["#D8F3DC", "#1B4332"],
    )
    apply_chart_style(fig, height=480, xaxis_title="最大車輛數", yaxis_title="Depot")
    fig.update_layout(coloraxis_showscale=False)
    fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(section_end(), unsafe_allow_html=True)


def _render_capacity_distribution(df: pd.DataFrame) -> None:
    st.markdown(section_start("容量分佈圖"), unsafe_allow_html=True)
    fig = px.histogram(
        df,
        x="max_vehicles",
        nbins=8,
        color_discrete_sequence=[GREEN_SEQUENCE[2]],
    )
    apply_chart_style(fig, height=280, xaxis_title="最大車輛數", yaxis_title="Depot 數量")
    st.plotly_chart(fig, use_container_width=True)

    top5 = df.nlargest(5, "max_vehicles")[["depot_name", "max_vehicles"]].copy()
    rest_total = max(df["max_vehicles"].sum() - top5["max_vehicles"].sum(), 0)
    if rest_total > 0:
        top5 = pd.concat([top5, pd.DataFrame({"depot_name": ["其他"], "max_vehicles": [rest_total]})], ignore_index=True)
    fig2 = px.pie(
        top5,
        values="max_vehicles",
        names="depot_name",
        color_discrete_sequence=GREEN_SEQUENCE,
    )
    apply_chart_style(fig2, height=300, showlegend=True)
    fig2.update_traces(textinfo="label+percent", textfont_size=11)
    st.plotly_chart(fig2, use_container_width=True)
    st.markdown(section_end(), unsafe_allow_html=True)


def _build_time_bucket_distribution(df: pd.DataFrame, col: str, grain_minutes: int) -> pd.DataFrame:
    if col not in df.columns:
        return pd.DataFrame()

    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return pd.DataFrame()

    bucket = (series // grain_minutes).astype(int) * grain_minutes
    dist = (
        bucket.value_counts()
        .sort_index()
        .rename_axis("bucket_start")
        .reset_index(name="count")
    )
    dist["bucket_label"] = dist["bucket_start"].apply(_format_minutes)
    return dist


def _format_minutes(minutes: float | int) -> str:
    total = int(minutes)
    hour = total // 60
    minute = total % 60
    return f"{hour:02d}:{minute:02d}"


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None
