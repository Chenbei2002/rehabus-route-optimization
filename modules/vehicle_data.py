"""Page 2 – 车辆数据: depot/parking, map, capacity charts, vehicle placeholder."""

from __future__ import annotations

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from utils.formatters import metric_card, page_header, section_start, section_end
from utils.styles import GREEN_SEQUENCE, apply_chart_style


# ------------------------------------------------------------------
# Public entry
# ------------------------------------------------------------------

def render_vehicle_data(parking_df: pd.DataFrame) -> None:
    st.markdown(
        page_header("车辆数据", "展示车辆资源、停车点分布、容量配置与 Depot 运营信息"),
        unsafe_allow_html=True,
    )

    _render_kpis(parking_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1])
    with col_left:
        _render_depot_table(parking_df)
    with col_right:
        _render_depot_map(parking_df)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    _render_capacity_charts(parking_df)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    _render_vehicle_placeholder()


# ------------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------------

def _render_kpis(df: pd.DataFrame) -> None:
    total_vehicles = int(df["max_vehicles"].sum())
    depot_count = len(df)
    avg_cap = total_vehicles / depot_count if depot_count else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card(f"{total_vehicles}", "车辆总数 (最大分配)"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card(depot_count, "停车点数量"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card(f"{total_vehicles}", "总停车容量"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card(f"{avg_cap:.1f}", "平均每 Depot 容量"), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Depot table
# ------------------------------------------------------------------

def _render_depot_table(df: pd.DataFrame) -> None:
    st.markdown(section_start("停车点信息表"), unsafe_allow_html=True)
    st.dataframe(
        df,
        use_container_width=True,
        height=480,
        column_config={
            "depot_code": "代码",
            "depot_name": "停车点名称",
            "lat": st.column_config.NumberColumn("纬度", format="%.6f"),
            "lon": st.column_config.NumberColumn("经度", format="%.6f"),
            "max_vehicles": "最大车辆数",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Folium map
# ------------------------------------------------------------------

def _render_depot_map(df: pd.DataFrame) -> None:
    st.markdown(section_start("停车点地图", "气泡大小反映容量"), unsafe_allow_html=True)

    map_df = df.dropna(subset=["lat", "lon"])
    center_lat = map_df["lat"].mean()
    center_lon = map_df["lon"].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="cartodbpositron",
    )

    for _, row in map_df.iterrows():
        radius = max(5, int(row["max_vehicles"]) * 0.9)
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=radius,
            popup=folium.Popup(
                f"<b>{row['depot_name']}</b><br>"
                f"代码: {row['depot_code']}<br>"
                f"最大车辆数: {row['max_vehicles']}",
                max_width=260,
            ),
            tooltip=f"{row['depot_name']} ({row['max_vehicles']}辆)",
            color="#2D6A4F",
            fill=True,
            fill_color="#40916C",
            fill_opacity=0.65,
        ).add_to(m)

    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    st_folium(m, use_container_width=True, height=450, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(section_end(), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Capacity charts
# ------------------------------------------------------------------

def _render_capacity_charts(df: pd.DataFrame) -> None:
    left, right = st.columns(2)

    with left:
        st.markdown(section_start("停车容量排序"), unsafe_allow_html=True)
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
        apply_chart_style(fig, height=520, xaxis_title="最大车辆数")
        fig.update_layout(coloraxis_showscale=False)
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)

    with right:
        st.markdown(section_start("容量分布"), unsafe_allow_html=True)
        fig = px.histogram(
            df, x="max_vehicles", nbins=8,
            color_discrete_sequence=[GREEN_SEQUENCE[2]],
        )
        apply_chart_style(fig, height=300, xaxis_title="最大车辆数", yaxis_title="Depot 数量")
        st.plotly_chart(fig, use_container_width=True)

        top5 = df.nlargest(5, "max_vehicles")[["depot_name", "max_vehicles"]].copy()
        rest_total = df["max_vehicles"].sum() - top5["max_vehicles"].sum()
        others = pd.DataFrame({"depot_name": ["其他"], "max_vehicles": [rest_total]})
        pie_df = pd.concat([top5, others], ignore_index=True)
        fig2 = px.pie(
            pie_df, values="max_vehicles", names="depot_name",
            color_discrete_sequence=GREEN_SEQUENCE,
        )
        apply_chart_style(fig2, height=320, showlegend=True)
        fig2.update_traces(textinfo="label+percent", textfont_size=11)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Vehicle-level placeholder
# ------------------------------------------------------------------

def _render_vehicle_placeholder() -> None:
    st.markdown(
        section_start("车辆资源详情", "此模块将在接入车辆级别数据后展示完整信息"),
        unsafe_allow_html=True,
    )

    st.info(
        "📌 **待接入数据字段：** 车辆编号、车辆类型、轮椅位容量、座位容量、"
        "所属 Depot、当前状态、是否可调度等。"
    )

    placeholder = pd.DataFrame(
        {
            "vehicle_id": ["RB-001", "RB-002", "RB-003", "RB-004", "RB-005"],
            "vehicle_type": ["标准复康巴士", "标准复康巴士", "小型复康巴士", "标准复康巴士", "小型复康巴士"],
            "wheelchair_capacity": [5, 5, 3, 5, 3],
            "seated_capacity": [10, 10, 6, 10, 6],
            "depot": ["KLB1", "SKW", "TM1", "FAL", "MEF"],
            "status": ["可调度", "可调度", "维修中", "可调度", "可调度"],
        }
    )
    st.dataframe(
        placeholder,
        use_container_width=True,
        column_config={
            "vehicle_id": "车辆编号",
            "vehicle_type": "车辆类型",
            "wheelchair_capacity": "轮椅位",
            "seated_capacity": "座位数",
            "depot": "所属 Depot",
            "status": "状态",
        },
    )
    st.caption("⬆️ 以上为示例数据结构，待替换为真实车辆数据。")
    st.markdown(section_end(), unsafe_allow_html=True)
