# -*- coding: utf-8 -*-
"""
Rehabus 路线可视化器 - Streamlit Cloud 部署版
"""

import os
import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="Rehabus 路线查看器", layout="wide")
st.title("🚌 Rehabus 上午路线查看器 (123条路线)")


@st.cache_data
def load_data():
    summary = pd.read_csv(os.path.join(BASE_DIR, "route_summary.csv"))
    detail = pd.read_csv(os.path.join(BASE_DIR, "route_detail.csv"))
    visits = pd.read_csv(os.path.join(BASE_DIR, "route_visits.csv"))

    # 从原始乘客数据获取站点经纬度和名称
    pax = pd.read_csv(os.path.join(BASE_DIR, "morning_passengers.csv"))
    stop_geo = {}
    for _, r in pax.iterrows():
        bid = int(r["board_stop_id"])
        aid = int(r["alight_stop_id"])
        if bid not in stop_geo:
            stop_geo[bid] = {
                "lat": float(r["board_lat"]),
                "lng": float(r["board_lng"]),
                "name": str(r.get("board_stop_name", bid)) if pd.notna(r.get("board_stop_name")) else str(bid),
            }
        if aid not in stop_geo:
            stop_geo[aid] = {
                "lat": float(r["alight_lat"]),
                "lng": float(r["alight_lng"]),
                "name": str(r.get("alight_stop_name", aid)) if pd.notna(r.get("alight_stop_name")) else str(aid),
            }
    return summary, detail, visits, stop_geo


summary, detail, visits, stop_geo = load_data()

# ── Sidebar: route selector ──
route_ids = sorted(summary["route_id"].unique())
summary_lookup = summary.set_index("route_id")

route_labels = []
for rid in route_ids:
    row = summary_lookup.loc[rid]
    pax_count = int(row["total_passengers"])
    duration = int(row["route_duration_min"])
    route_labels.append(f"{rid}  ({pax_count}人, {duration}min)")

selected_label = st.sidebar.selectbox("选择路线", route_labels, index=0)
selected_route = route_ids[route_labels.index(selected_label)]

# ── Sidebar: overview stats ──
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 总览")
st.sidebar.metric("路线总数", len(route_ids))
st.sidebar.metric("总人数", int(summary["total_passengers"].sum()))
st.sidebar.metric("平均人数/路线", f"{summary['total_passengers'].mean():.1f}")
st.sidebar.metric("平均时长", f"{summary['route_duration_min'].mean():.0f}min")

# ── Route data ──
rv = visits[visits["route_id"] == selected_route].sort_values("visit_seq").copy()
rd = detail[detail["route_id"] == selected_route].copy()
rs = summary_lookup.loc[selected_route]

# ── Summary metrics ──
st.subheader(f"路线 {selected_route} 概况")

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("乘客人数", int(rs["total_passengers"]))
col2.metric("轮椅", int(rs["total_wheelchair"]))
col3.metric("非轮椅", int(rs["total_non_wheelchair"]))
col4.metric("路线时长", f"{int(rs['route_duration_min'])}min")
col5.metric("提前出发", f"{int(rs['early_departure_shift_min'])}min")
col6.metric("车上峰值", int(rs["peak_total_onboard"]))

# ── Stop sequence table ──
st.subheader("📋 站点停靠顺序")

stop_visits_list = []
current_stop = None

for _, row in rv.iterrows():
    sid = int(row["stop_id"])
    if current_stop is None or current_stop["stop_id"] != sid:
        current_stop = {
            "stop_id": sid,
            "arrival": row["vehicle_arrival_time"],
            "departure": row["vehicle_departure_time"],
            "travel_min": row["travel_from_prev_stop_min"],
            "service_min": row["service_time_min"],
            "pickups": [],
            "dropoffs": [],
        }
        stop_visits_list.append(current_stop)

    if row["event_type"] == "pickup":
        current_stop["pickups"].append(row["individual_name"])
    else:
        current_stop["dropoffs"].append(row["individual_name"])
    current_stop["departure"] = row["vehicle_departure_time"]

table_rows = []
for i, sv in enumerate(stop_visits_list):
    sid = sv["stop_id"]
    geo = stop_geo.get(sid, {})
    name = geo.get("name", str(sid))
    pickup_names = ", ".join(sv["pickups"]) if sv["pickups"] else ""
    dropoff_names = ", ".join(sv["dropoffs"]) if sv["dropoffs"] else ""
    table_rows.append({
        "序号": i + 1,
        "站点ID": sid,
        "站点名称": name if len(str(name)) < 35 else str(name)[:33] + "…",
        "到达": sv["arrival"],
        "离开": sv["departure"],
        "行驶(min)": round(float(sv["travel_min"]), 1),
        "服务(min)": round(float(sv["service_min"]), 1),
        "上车": f"↑{len(sv['pickups'])}" if sv["pickups"] else "",
        "上车乘客": pickup_names,
        "下车": f"↓{len(sv['dropoffs'])}" if sv["dropoffs"] else "",
        "下车乘客": dropoff_names,
    })

st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True, height=400)

# ── Map ──
st.subheader("🗺️ 路线地图")

map_points = []
for i, sv in enumerate(stop_visits_list):
    sid = sv["stop_id"]
    geo = stop_geo.get(sid)
    if geo is None:
        continue
    pu = len(sv["pickups"])
    do = len(sv["dropoffs"])
    label_parts = []
    if pu:
        label_parts.append(f"↑{pu}")
    if do:
        label_parts.append(f"↓{do}")
    map_points.append({
        "seq": i + 1,
        "lat": geo["lat"],
        "lon": geo["lng"],
        "stop_id": sid,
        "name": geo.get("name", str(sid)),
        "label": f"#{i+1} " + " ".join(label_parts),
        "pickups": pu,
        "dropoffs": do,
        "arrival": sv["arrival"],
    })

if map_points:
    import pydeck as pdk

    df_map = pd.DataFrame(map_points)

    def get_color(row):
        if row["pickups"] > 0 and row["dropoffs"] > 0:
            return [50, 50, 255, 200]
        elif row["pickups"] > 0:
            return [0, 180, 0, 200]
        else:
            return [220, 30, 30, 200]

    df_map["color"] = df_map.apply(get_color, axis=1)
    df_map["radius"] = df_map.apply(lambda r: 100 + 50 * (r["pickups"] + r["dropoffs"]), axis=1)
    df_map["tooltip"] = df_map.apply(
        lambda r: f"#{r['seq']} {r['name']}\n到达: {r['arrival']}\n上车:{r['pickups']} 下车:{r['dropoffs']}", axis=1
    )

    line_coords = [[p["lon"], p["lat"]] for p in map_points]
    line_data = [{"path": line_coords}]

    center_lat = df_map["lat"].mean()
    center_lon = df_map["lon"].mean()

    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["lon", "lat"],
        get_radius="radius",
        get_fill_color="color",
        pickable=True,
    )

    path_layer = pdk.Layer(
        "PathLayer",
        data=line_data,
        get_path="path",
        get_color=[80, 80, 80, 160],
        width_min_pixels=2,
        get_width=3,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position=["lon", "lat"],
        get_text="label",
        get_size=13,
        get_color=[0, 0, 0, 255],
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0, -18],
        pickable=False,
    )

    view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=12.5, pitch=0)

    deck = pdk.Deck(
        layers=[path_layer, scatter_layer, text_layer],
        initial_view_state=view,
        tooltip={"text": "{tooltip}"},
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )

    st.pydeck_chart(deck, use_container_width=True, height=550)
    st.caption("🟢 上车站 | 🔴 下车站 | 🔵 混合站 | 圆点大小 = 上下车人数")
else:
    st.warning("该路线的站点缺少经纬度数据，无法显示地图。")

# ── Passenger detail ──
st.subheader("👤 乘客明细")

show_cols = [
    "individual_name", "is_wheelchair",
    "pickup_stop_id", "dropoff_stop_id",
    "planned_pickup_time", "planned_dropoff_time",
    "actual_pickup_time", "actual_dropoff_time",
    "total_ride_time_min", "direct_drive_time_min",
    "detour_time_min", "dropoff_delay_min",
]
col_rename = {
    "individual_name": "乘客",
    "is_wheelchair": "轮椅",
    "pickup_stop_id": "上车站",
    "dropoff_stop_id": "下车站",
    "planned_pickup_time": "计划上车",
    "planned_dropoff_time": "计划下车",
    "actual_pickup_time": "实际上车",
    "actual_dropoff_time": "实际下车",
    "total_ride_time_min": "乘车时间(min)",
    "direct_drive_time_min": "直达时间(min)",
    "detour_time_min": "绕路(min)",
    "dropoff_delay_min": "迟到(min)",
}

display_df = rd[show_cols].rename(columns=col_rename)
st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── Route comparison ──
with st.expander("📊 全部路线对比", expanded=False):
    compare_df = summary.copy()
    compare_df = compare_df.rename(columns={
        "route_id": "路线",
        "num_records": "记录数",
        "total_passengers": "总人数",
        "total_wheelchair": "轮椅",
        "total_non_wheelchair": "非轮椅",
        "route_duration_min": "时长(min)",
        "early_departure_shift_min": "提前出发(min)",
        "peak_total_onboard": "峰值载客",
    })
    st.dataframe(
        compare_df[["路线", "总人数", "轮椅", "非轮椅", "时长(min)", "提前出发(min)", "峰值载客"]],
        use_container_width=True, hide_index=True, height=400
    )
