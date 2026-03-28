"""Rehabus Route Optimization Dashboard – main entry point.

Run with:
    streamlit run main.py
"""

import streamlit as st

from modules.basic_data import render_basic_data
from modules.vehicle_data import render_vehicle_data
from modules.route_planning import render_route_planning
from utils.data_loader import load_passenger_data, load_parking_data, apply_filters
from utils.styles import get_css


# ------------------------------------------------------------------
# Sidebar: global filters
# ------------------------------------------------------------------

def _render_sidebar(passenger_df):
    """Build sidebar filter widgets and return selected values."""
    with st.sidebar:
        st.markdown("### 📋 数据筛选")
        st.caption("全局筛选条件，影响所有页面数据展示")
        st.divider()

        all_types = sorted(passenger_df["passenger_type"].dropna().unique().tolist())
        selected_types = st.multiselect(
            "客户种类 (Passenger Type)", options=all_types, default=[], key="f_type",
        )

        all_purposes = sorted(passenger_df["purpose"].dropna().unique().tolist())
        selected_purposes = st.multiselect(
            "用途 (Purpose)", options=all_purposes, default=[], key="f_purpose",
        )

        all_districts = sorted(
            set(
                passenger_df["board_district"].dropna().unique().tolist()
                + passenger_df["alight_district"].dropna().unique().tolist()
            )
        )
        selected_districts = st.multiselect(
            "区域 (District)", options=all_districts, default=[], key="f_district",
        )

        all_routes = sorted(passenger_df["existing_route"].dropna().unique().tolist())
        selected_routes = st.multiselect(
            "路线 (Route)", options=all_routes, default=[], key="f_route",
        )

        all_days = sorted(passenger_df["day_pattern"].dropna().astype(str).unique().tolist())
        selected_days = st.multiselect(
            "日期模式 (Day Pattern)", options=all_days, default=[], key="f_day",
        )

        st.divider()
        if st.button("🔄 重置筛选", use_container_width=True):
            for k in ("f_type", "f_purpose", "f_district", "f_route", "f_day"):
                st.session_state[k] = []
            st.rerun()

    return {
        "passenger_types": selected_types or None,
        "purposes": selected_purposes or None,
        "districts": selected_districts or None,
        "routes": selected_routes or None,
        "day_patterns": selected_days or None,
    }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Rehabus Route Optimization Dashboard",
        page_icon="🚌",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(get_css(), unsafe_allow_html=True)

    st.markdown(
        '<div class="main-title">Rehabus Route Optimization Dashboard</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">复康巴士路线优化与调度管理平台</div>',
        unsafe_allow_html=True,
    )

    # Data loading (cached)
    passenger_df = load_passenger_data()
    parking_df = load_parking_data()

    # Sidebar filters
    filters = _render_sidebar(passenger_df)
    filtered_df = apply_filters(passenger_df, **filters)

    # Top navigation tabs
    tab_basic, tab_vehicle, tab_route = st.tabs(
        ["📊 基础数据", "🚌 车辆数据", "🧭 路线规划"]
    )

    with tab_basic:
        render_basic_data(filtered_df, passenger_df)

    with tab_vehicle:
        render_vehicle_data(parking_df)

    with tab_route:
        render_route_planning(filtered_df, passenger_df, parking_df)


if __name__ == "__main__":
    main()
