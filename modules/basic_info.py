import streamlit as st


def render_kpis():
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">132</div>
                <div class="metric-label">现有路线数</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">1200+</div>
                <div class="metric-label">服务用户数</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">85%</div>
                <div class="metric-label">车辆利用率</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def render_basic_data() -> None:
    st.header("1) 基础数据")
    st.caption("后续补充基础数据上传、清洗、筛选与可视化。")
    render_kpis()

