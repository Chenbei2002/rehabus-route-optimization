"""Rehabus Route Optimization Dashboard – main entry point.

Run with:
    streamlit run main.py
"""

import streamlit as st

from modules.basic_data import render_basic_data
from modules.old_data_preview import render_old_data_preview
from modules.vehicle_data import render_vehicle_data
from modules.route_planning import render_route_planning
from utils.data_loader import load_passenger_data, load_parking_data
from utils.styles import get_css


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
        '<div class="sub-title">復康巴士路線優化與調度管理平台</div>',
        unsafe_allow_html=True,
    )

    # Data loading (cached)
    passenger_df = load_passenger_data()
    parking_df = load_parking_data()

    # Top navigation tabs
    tab_old, tab_basic, tab_vehicle, tab_route = st.tabs(
        ["📁 舊資料預覽", "📊 基礎資料", "🚌 車輛資料", "🧭 路線規劃"]
    )

    with tab_old:
        render_old_data_preview()

    with tab_basic:
        render_basic_data(passenger_df, passenger_df)

    with tab_vehicle:
        render_vehicle_data(parking_df, passenger_df)

    with tab_route:
        render_route_planning(passenger_df, passenger_df, parking_df)


if __name__ == "__main__":
    main()
