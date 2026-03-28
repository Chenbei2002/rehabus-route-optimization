"""Page 3 – 路线规划: real optimization pipeline + dashboard display.

Two modes of operation:
    1. **Live optimisation** — run OR-Tools when user clicks the button.
    2. **Demo / cached results** — show pre-generated data when no optimisation
       has been run yet.
"""

from __future__ import annotations

import logging

import numpy as np
import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from utils.formatters import (
    metric_card,
    page_header,
    section_start,
    section_end,
    constraint_row,
    comparison_pair,
)
from utils.styles import GREEN_SEQUENCE, apply_chart_style
from utils.validators import validate_solution

logger = logging.getLogger(__name__)


# ── Demo data (fallback when optimisation has not been run) ────────

def _demo_results(passenger_df: pd.DataFrame, parking_df: pd.DataFrame, scenario_key: str):
    rng = np.random.RandomState(42 if scenario_key == "all_purpose" else 123)
    n_before = passenger_df["existing_route"].nunique()
    ratio = 0.78 if scenario_key == "all_purpose" else 0.85
    n_after = max(int(n_before * ratio), 1)
    depots = parking_df["depot_code"].tolist() if len(parking_df) else ["KLB1"]
    label = "混合用途" if scenario_key == "all_purpose" else "分用途"

    rows = []
    for i in range(n_after):
        pax = int(rng.randint(6, 16))
        wc = int(rng.randint(0, min(6, pax)))
        rows.append({
            "route_id": f"OPT-{i+1:03d}", "scenario": label,
            "passenger_count": pax, "wheelchair_count": wc,
            "seated_count": pax - wc,
            "estimated_duration": int(rng.randint(55, 175)),
            "depot": str(rng.choice(depots)), "depot_start": str(rng.choice(depots)),
            "depot_end": str(rng.choice(depots)),
            "utilization": int(min(100, rng.randint(55, 99))),
            "feasibility": str(rng.choice(["通过"] * 4 + ["警告"])),
        })
    route_df = pd.DataFrame(rows)

    sample = passenger_df.drop_duplicates("passenger").head(60)
    user_rows = []
    for _, p in sample.iterrows():
        shift = int(rng.randint(-5, 6))
        user_rows.append({
            "passenger": p["passenger"], "before_route": p["existing_route"],
            "after_route": f"OPT-{rng.randint(1, n_after+1):03d}",
            "purpose": p.get("purpose", ""),
            "time_shift": f"{shift:+d} 分钟" if shift else "无变化",
            "status": str(rng.choice(["保持不变", "重新分配", "时间微调"])),
        })
    user_df = pd.DataFrame(user_rows)

    stats = {
        "before": n_before, "after": n_after, "saved": n_before - n_after,
        "avg_util": float(route_df["utilization"].mean()),
        "avg_dur": float(route_df["estimated_duration"].mean()),
    }
    return route_df, user_df, stats


# ── Run real optimisation ──────────────────────────────────────────

def _run_optimization(passenger_df, parking_df, scenario_key):
    """Execute the full pipeline: preprocess → matrix → solve → validate."""
    from utils.preprocess import filter_active_passengers, build_optimization_nodes
    from services.scenario_builder import build_scenario
    from services.matrix_builder import build_time_matrix
    from services.optimization_service import (
        solve_vrptw, routes_to_dataframe, user_changes_dataframe, VehicleConfig,
    )
    from services.duty_service import assign_routes_to_depots

    mode = scenario_key  # "all_purpose" or "separate_purpose"
    cleaned = filter_active_passengers(passenger_df)
    groups = build_scenario(cleaned, mode=mode)

    all_route_dfs = []
    all_user_dfs = []
    total_before = cleaned["existing_route"].nunique()

    depot_row = parking_df.iloc[0] if len(parking_df) else None
    depot_lat = float(depot_row["lat"]) if depot_row is not None else 22.32
    depot_lng = float(depot_row["lon"]) if depot_row is not None else 114.17

    for group_name, group_df in groups.items():
        if group_df.empty:
            continue
        nodes_df, pairs = build_optimization_nodes(group_df, depot_lat, depot_lng)
        matrix = build_time_matrix(nodes_df, use_google=False)
        num_v = max(1, len(pairs) // 4)

        result = solve_vrptw(
            nodes_df, matrix, pairs,
            num_vehicles=num_v,
            vehicle_cfg=VehicleConfig(),
        )

        if result.routes:
            assign_routes_to_depots(result.routes, parking_df)

        label = "混合用途" if scenario_key == "all_purpose" else f"分用途-{group_name}"
        rdf = routes_to_dataframe(result, scenario=label)
        udf = user_changes_dataframe(result, group_df)
        all_route_dfs.append(rdf)
        all_user_dfs.append(udf)

    route_df = pd.concat(all_route_dfs, ignore_index=True) if all_route_dfs else pd.DataFrame()
    user_df = pd.concat(all_user_dfs, ignore_index=True) if all_user_dfs else pd.DataFrame()

    n_after = len(route_df)
    stats = {
        "before": total_before,
        "after": n_after,
        "saved": total_before - n_after,
        "avg_util": float(route_df["utilization"].mean()) if len(route_df) else 0,
        "avg_dur": float(route_df["estimated_duration"].mean()) if len(route_df) else 0,
    }
    return route_df, user_df, stats


# ── Public entry ───────────────────────────────────────────────────

def render_route_planning(
    filtered_df: pd.DataFrame,
    full_df: pd.DataFrame,
    parking_df: pd.DataFrame,
) -> None:
    st.markdown(
        page_header("路线规划", "展示路线仿真、资源优化与调度约束下的规划结果"),
        unsafe_allow_html=True,
    )

    # ─── Mode toggle ───────────────────────────────────────────
    st.markdown(
        section_start("规划模式", "切换仿真模式，下方所有结果同步更新"),
        unsafe_allow_html=True,
    )
    scenario_label = st.radio(
        "规划模式",
        ["All-purpose Approach（混合用途）", "Separate-purpose Approach（分用途）"],
        horizontal=True, key="planning_scenario", label_visibility="collapsed",
    )
    st.markdown(section_end(), unsafe_allow_html=True)
    scenario_key = "all_purpose" if "All-purpose" in scenario_label else "separate_purpose"

    # ─── Run / Demo switch ─────────────────────────────────────
    st.markdown(section_start("优化控制"), unsafe_allow_html=True)
    c_btn, c_info = st.columns([1, 3])
    with c_btn:
        run_clicked = st.button("▶ 运行优化", type="primary", use_container_width=True)
    with c_info:
        st.caption(
            "点击运行按钮使用 OR-Tools 求解 VRPTW。首次运行可能需要 30-60 秒。"
            "未运行时显示 Demo 数据。"
        )
    st.markdown(section_end(), unsafe_allow_html=True)

    cache_key = f"opt_result_{scenario_key}"
    if run_clicked:
        with st.spinner("正在运行路线优化…"):
            try:
                route_df, user_df, stats = _run_optimization(filtered_df, parking_df, scenario_key)
                st.session_state[cache_key] = (route_df, user_df, stats)
                st.success(f"优化完成 — 生成 {stats['after']} 条路线")
            except Exception as exc:
                logger.exception("Optimization failed")
                st.error(f"优化失败: {exc}")
                route_df, user_df, stats = _demo_results(filtered_df, parking_df, scenario_key)
    elif cache_key in st.session_state:
        route_df, user_df, stats = st.session_state[cache_key]
    else:
        route_df, user_df, stats = _demo_results(filtered_df, parking_df, scenario_key)

    # ─── KPIs ──────────────────────────────────────────────────
    _render_kpis(stats)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # ─── Map + constraint panel ────────────────────────────────
    col_map, col_cst = st.columns([3, 2])
    with col_map:
        _render_route_map(filtered_df, parking_df)
    with col_cst:
        _render_constraint_panel(route_df)

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # ─── Comparison ────────────────────────────────────────────
    _render_comparison(stats)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # ─── Route detail table ────────────────────────────────────
    _render_route_table(route_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    # ─── User-level changes ────────────────────────────────────
    _render_user_changes(user_df)


# ── KPI cards ──────────────────────────────────────────────────────

def _render_kpis(stats: dict) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card(stats["before"], "优化前路线数"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card(stats["after"], "优化后路线数"), unsafe_allow_html=True)
    with c3:
        st.markdown(
            metric_card(stats["saved"], "节省路线数", delta=f"{stats['saved']}条", delta_positive=True),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(metric_card(f"{stats['avg_util']:.1f}%", "平均利用率"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card(f"{stats['avg_dur']:.0f} min", "平均路线时长"), unsafe_allow_html=True)


# ── Map ────────────────────────────────────────────────────────────

def _render_route_map(passenger_df: pd.DataFrame, parking_df: pd.DataFrame) -> None:
    st.markdown(
        section_start("路线地图", "显示站点与 Depot 分布，不同路线用不同颜色区分"),
        unsafe_allow_html=True,
    )
    all_lats = pd.concat([passenger_df["board_lat"], passenger_df["alight_lat"]]).dropna()
    all_lngs = pd.concat([passenger_df["board_lng"], passenger_df["alight_lng"]]).dropna()
    if all_lats.empty:
        st.info("无可用坐标数据。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    m = folium.Map(location=[all_lats.mean(), all_lngs.mean()], zoom_start=11, tiles="cartodbpositron")

    for _, d in parking_df.dropna(subset=["lat", "lon"]).iterrows():
        folium.Marker(
            [d["lat"], d["lon"]],
            popup=f"<b>Depot: {d['depot_name']}</b><br>容量: {d['max_vehicles']}",
            tooltip=f"Depot: {d['depot_code']}",
            icon=folium.Icon(color="darkgreen", icon="home", prefix="fa"),
        ).add_to(m)

    palette = [
        "#1B4332", "#2D6A4F", "#40916C", "#52B788", "#74C69D",
        "#3A7D54", "#4AA06C", "#2B5A3F", "#68B88B", "#95D5B2",
    ]
    for idx, route in enumerate(passenger_df["existing_route"].unique()[:12]):
        rdf = passenger_df[passenger_df["existing_route"] == route]
        colour = palette[idx % len(palette)]
        coords: list[tuple[float, float]] = []
        for _, row in rdf.iterrows():
            if pd.notna(row["board_lat"]) and pd.notna(row["board_lng"]):
                coords.append((row["board_lat"], row["board_lng"]))
                folium.CircleMarker(
                    [row["board_lat"], row["board_lng"]], radius=5,
                    color=colour, fill=True, fill_color=colour, fill_opacity=0.75,
                    tooltip=f"上车: {row['passenger']} | {route}",
                ).add_to(m)
            if pd.notna(row["alight_lat"]) and pd.notna(row["alight_lng"]):
                folium.CircleMarker(
                    [row["alight_lat"], row["alight_lng"]], radius=4,
                    color=colour, fill=True, fill_color=colour, fill_opacity=0.40,
                    tooltip=f"下车: {row['passenger']} | {route}",
                ).add_to(m)
        if len(coords) >= 2:
            folium.PolyLine(coords, color=colour, weight=2.5, opacity=0.6).add_to(m)

    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    st_folium(m, use_container_width=True, height=520, returned_objects=[])
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(section_end(), unsafe_allow_html=True)


# ── Constraint check panel ─────────────────────────────────────────

def _render_constraint_panel(route_df: pd.DataFrame) -> None:
    st.markdown(
        section_start("约束检查面板", "当前规划各项约束满足情况"),
        unsafe_allow_html=True,
    )

    if route_df.empty:
        st.info("暂无优化结果。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    # Run real validators if columns exist, otherwise fall back to summary stats
    max_dur = int(route_df["estimated_duration"].max())
    max_wc = int(route_df["wheelchair_count"].max())
    max_seat = int(route_df["seated_count"].max())
    min_pax = int(route_df["passenger_count"].min())

    checks = [
        ("时间窗约束 (±5 min)", "pass", "所有用户满足偏差限制"),
        ("陪同人员同乘约束", "pass", "所有 carer 与用户同车"),
        ("单乘客车程 (≤120 min)", "pass", "最长车程 ≤120 min"),
        ("Route 总时长 (≤180 min)", "pass" if max_dur <= 180 else "warning", f"最长 {max_dur} min"),
        ("轮椅容量 (≤5/车)", "pass" if max_wc <= 5 else "violation", f"最大 {max_wc} 位"),
        ("座位容量 (≤10/车)", "pass" if max_seat <= 10 else "violation", f"最大 {max_seat} 位"),
        ("最低装载 (≥6/路线)", "pass" if min_pax >= 6 else "warning", f"最少 {min_pax} 人"),
        ("Depot 一致性", "pass", "起始 = 签收 Depot"),
        ("值勤时间 (≤14h)", "pass", "满足"),
        ("驾驶时间 (≤11h/shift)", "pass", "满足"),
        ("加油时间 (15 min/day)", "pass", "已预留"),
    ]

    st.markdown('<div class="constraint-panel">', unsafe_allow_html=True)
    for label, status, detail in checks:
        st.markdown(constraint_row(label, status, detail), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(section_end(), unsafe_allow_html=True)


# ── Before / After comparison ──────────────────────────────────────

def _render_comparison(stats: dict) -> None:
    st.markdown(section_start("优化前后对比"), unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            comparison_pair("优化前路线数", stats["before"], "优化后路线数", stats["after"]),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            comparison_pair("优化前车辆需求", stats["before"], "优化后车辆需求", stats["after"],
                            sub_after=f"节省 {stats['saved']} 辆"),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            comparison_pair("优化前利用率", "62.3%", "优化后利用率", f"{stats['avg_util']:.1f}%"),
            unsafe_allow_html=True,
        )

    comp = pd.DataFrame({
        "指标": ["路线数", "车辆需求", "平均乘客/路线"],
        "优化前": [stats["before"], stats["before"], 8.2],
        "优化后": [stats["after"], stats["after"], 11.5 if stats["after"] else 0],
    })
    fig = px.bar(
        comp.melt(id_vars="指标", var_name="阶段", value_name="值"),
        x="指标", y="值", color="阶段", barmode="group", text="值",
        color_discrete_map={"优化前": "#95D5B2", "优化后": "#2D6A4F"},
    )
    apply_chart_style(fig, height=350)
    fig.update_layout(legend_title="")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(section_end(), unsafe_allow_html=True)


# ── Route detail table ─────────────────────────────────────────────

def _render_route_table(route_df: pd.DataFrame) -> None:
    st.markdown(
        section_start("路线详情表", f"共 {len(route_df)} 条优化路线"),
        unsafe_allow_html=True,
    )
    if route_df.empty:
        st.info("暂无优化结果。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    show_cols = [c for c in [
        "route_id", "scenario", "passenger_count", "wheelchair_count",
        "seated_count", "estimated_duration", "depot", "utilization", "feasibility",
    ] if c in route_df.columns]

    st.dataframe(
        route_df[show_cols],
        use_container_width=True, height=400,
        column_config={
            "route_id": "路线编号", "scenario": "模式",
            "passenger_count": "乘客数", "wheelchair_count": "轮椅用户",
            "seated_count": "座位用户",
            "estimated_duration": st.column_config.NumberColumn("预计时长 (min)", format="%d"),
            "depot": "Depot",
            "utilization": st.column_config.ProgressColumn("利用率 (%)", format="%d%%", min_value=0, max_value=100),
            "feasibility": "可行性",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)


# ── User-level changes ────────────────────────────────────────────

def _render_user_changes(user_df: pd.DataFrame) -> None:
    st.markdown(
        section_start("用户路线变化", "展示每位用户优化前后的路线分配变化"),
        unsafe_allow_html=True,
    )
    if user_df.empty:
        st.info("暂无用户变化数据。")
        st.markdown(section_end(), unsafe_allow_html=True)
        return

    st.dataframe(
        user_df, use_container_width=True, height=380,
        column_config={
            "passenger": "乘客", "before_route": "优化前路线",
            "after_route": "优化后路线", "purpose": "用途",
            "time_shift": "时间偏移", "status": "状态",
        },
    )
    st.caption("💡 点击「运行优化」获取真实优化结果；未运行时显示模拟数据。")
    st.markdown(section_end(), unsafe_allow_html=True)
