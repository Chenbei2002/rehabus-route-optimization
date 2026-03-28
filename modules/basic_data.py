"""Page 1 – 基础数据: passenger overview, interactive exploration, charts."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import get_route_summary
from utils.formatters import metric_card, page_header, section_start, section_end
from utils.styles import GREEN_SEQUENCE, apply_chart_style


# ------------------------------------------------------------------
# Public entry
# ------------------------------------------------------------------

def render_basic_data(filtered_df: pd.DataFrame, full_df: pd.DataFrame) -> None:
    st.markdown(
        page_header("基础数据", "客户基础信息总览与交互探索"),
        unsafe_allow_html=True,
    )

    if filtered_df.empty:
        st.warning("当前筛选条件下无数据，请调整侧边栏筛选器。")
        return

    _render_kpis(filtered_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    explore_df = _render_category_explorer(filtered_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    _render_charts(explore_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    _render_detail_table(explore_df)
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    _render_route_overview(explore_df)


# ------------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------------

def _render_kpis(df: pd.DataFrame) -> None:
    total_passengers = df["passenger"].nunique()
    total_routes = df["existing_route"].nunique()
    all_stops = set(df["board_stop"].dropna()) | set(df["alight_stop"].dropna())
    active_count = df.loc[df["is_active"] == True, "passenger"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card(f"{total_passengers:,}", "用户总数"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card(total_routes, "现有路线数"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card(f"{len(all_stops):,}", "站点数"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card(f"{active_count:,}", "活跃用户数"), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Interactive category explorer
# ------------------------------------------------------------------

def _render_category_explorer(df: pd.DataFrame) -> pd.DataFrame:
    st.markdown(
        section_start("客户分类交互", "选择用途分类，下方图表与表格同步刷新"),
        unsafe_allow_html=True,
    )

    purposes = sorted(df["purpose"].dropna().unique().tolist())
    options = ["全部"] + purposes
    selected = st.radio(
        "用途分类",
        options,
        horizontal=True,
        key="explore_purpose",
        label_visibility="collapsed",
    )

    explore_df = df if selected == "全部" else df[df["purpose"] == selected]

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("乘客数", f"{explore_df['passenger'].nunique():,}")
    with mc2:
        st.metric("路线数", explore_df["existing_route"].nunique())
    with mc3:
        st.metric("轮椅用户", int(explore_df["is_wheelchair"].sum()))
    with mc4:
        avg_trip = explore_df["trip_duration_minutes_est"].mean()
        st.metric("平均车程 (分钟)", f"{avg_trip:.0f}" if pd.notna(avg_trip) else "—")

    show_cols = [
        "passenger", "passenger_type", "existing_route",
        "board_stop", "alight_stop", "day_pattern",
        "board_time_str", "alight_time_str",
    ]
    show_cols = [c for c in show_cols if c in explore_df.columns]
    st.dataframe(
        explore_df[show_cols].head(80),
        use_container_width=True,
        height=280,
        column_config={
            "passenger": "乘客",
            "passenger_type": "类型",
            "existing_route": "路线",
            "board_stop": "上车站",
            "alight_stop": "下车站",
            "day_pattern": "日期模式",
            "board_time_str": "上车时间",
            "alight_time_str": "下车时间",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)
    return explore_df


# ------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------

def _render_charts(df: pd.DataFrame) -> None:
    left, right = st.columns(2)

    with left:
        st.markdown(section_start("用途分布"), unsafe_allow_html=True)
        purpose_ct = (
            df.groupby("purpose")["passenger"]
            .nunique()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        fig = px.bar(
            purpose_ct, x="purpose", y="count", text="count",
            color_discrete_sequence=GREEN_SEQUENCE[1:],
        )
        apply_chart_style(fig, yaxis_title="乘客数")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)

    with right:
        st.markdown(section_start("区域分布 (上车)"), unsafe_allow_html=True)
        dist_ct = (
            df.groupby("board_district")["passenger"]
            .nunique()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .head(15)
        )
        fig = px.bar(
            dist_ct, x="count", y="board_district", orientation="h", text="count",
            color_discrete_sequence=[GREEN_SEQUENCE[2]],
        )
        apply_chart_style(fig, xaxis_title="乘客数")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)

    left2, right2 = st.columns(2)

    with left2:
        st.markdown(section_start("路线乘客数分布 (Top 20)"), unsafe_allow_html=True)
        route_ct = (
            df.groupby("existing_route")["passenger"]
            .nunique()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .head(20)
        )
        fig = px.bar(
            route_ct, x="existing_route", y="count", text="count",
            color_discrete_sequence=[GREEN_SEQUENCE[3]],
        )
        apply_chart_style(fig, xaxis_title="路线", yaxis_title="乘客数")
        fig.update_traces(textposition="outside")
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)

    with right2:
        st.markdown(section_start("服务日模式分布"), unsafe_allow_html=True)
        day_ct = (
            df.groupby(df["day_pattern"].astype(str))["passenger"]
            .nunique()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        fig = px.pie(
            day_ct, values="count", names="day_pattern",
            color_discrete_sequence=GREEN_SEQUENCE,
        )
        apply_chart_style(fig, showlegend=True)
        fig.update_traces(textinfo="label+percent", textfont_size=12)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(section_end(), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Detail table
# ------------------------------------------------------------------

def _render_detail_table(df: pd.DataFrame) -> None:
    st.markdown(
        section_start("用户明细表", f"共 {len(df):,} 条记录"),
        unsafe_allow_html=True,
    )
    cols = [
        "passenger", "purpose", "passenger_type", "existing_route",
        "board_stop", "alight_stop", "day_pattern",
        "board_time_str", "alight_time_str", "trip_duration_minutes_est",
    ]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(
        df[cols],
        use_container_width=True,
        height=420,
        column_config={
            "passenger": "乘客",
            "purpose": "用途",
            "passenger_type": "类型",
            "existing_route": "路线",
            "board_stop": "上车站",
            "alight_stop": "下车站",
            "day_pattern": "日期模式",
            "board_time_str": "上车时间",
            "alight_time_str": "下车时间",
            "trip_duration_minutes_est": st.column_config.NumberColumn(
                "预计车程 (分钟)", format="%.0f"
            ),
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Route & stop overview
# ------------------------------------------------------------------

def _render_route_overview(df: pd.DataFrame) -> None:
    st.markdown(
        section_start("路线与站点概览", "每条路线的乘客数、站点数与用途汇总"),
        unsafe_allow_html=True,
    )
    summary = get_route_summary(df)
    st.dataframe(
        summary,
        use_container_width=True,
        height=380,
        column_config={
            "route": "路线",
            "passenger_count": "乘客数",
            "wheelchair_count": "轮椅用户",
            "seated_count": "座位用户",
            "unique_board_stops": "上车站点数",
            "unique_alight_stops": "下车站点数",
            "avg_trip_duration": st.column_config.NumberColumn(
                "平均车程 (分钟)", format="%.1f"
            ),
            "purposes": "用途",
        },
    )
    st.markdown(section_end(), unsafe_allow_html=True)
