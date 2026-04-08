import streamlit as st


def render_kpis():
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">132</div>
                <div class="metric-label">現有路線數</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">1200+</div>
                <div class="metric-label">服務用戶數</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="metric-card">
                <div class="metric-value">85%</div>
                <div class="metric-label">車輛利用率</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def render_basic_data() -> None:
    st.header("1) 基礎資料")
    st.caption("後續補充基礎資料上傳、清洗、篩選與視覺化。")
    render_kpis()

