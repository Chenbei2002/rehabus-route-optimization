from pathlib import Path

import pandas as pd
import streamlit as st


def render_parking_data() -> None:
    st.header("2) Parking 頁面")
    st.caption("展示 Depot 停車點及容量資訊。")

    data_path = Path(__file__).resolve().parent.parent / "parking_data.csv"
    df = pd.read_csv(data_path)

    st.subheader("📊 Parking Data")
    st.dataframe(df, use_container_width=True)

    map_df = df.dropna(subset=["lat", "lon"])
    st.subheader("📍 Map View")
    st.map(map_df[["lat", "lon"]])

    st.subheader("📋 Location Details")
    for _, row in map_df.iterrows():
        st.write(
            f"**{row['Depot Name']}** "
            f"(Code: {row['ABB.']}) | "
            f"Vehicles: {row['Max number of vehicle allocated']}"
        )
