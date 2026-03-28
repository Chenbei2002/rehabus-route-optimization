"""Centralized CSS theme for the Rehabus Route Optimization Dashboard."""

COLORS = {
    "deep_green": "#1B4332",
    "primary": "#2D6A4F",
    "accent": "#40916C",
    "medium": "#52B788",
    "light": "#74C69D",
    "pale": "#95D5B2",
    "soft": "#B7E4C7",
    "bg_green": "#D8F3DC",
    "page_bg": "#F6FBF7",
    "white": "#FFFFFF",
    "text_primary": "#1B4332",
    "text_secondary": "#52796F",
    "text_muted": "#8FA9A0",
    "border": "#E0EDE5",
    "shadow": "rgba(27, 67, 50, 0.08)",
    "pass": "#2D6A4F",
    "warning": "#E9A820",
    "violation": "#D64045",
}

GREEN_SEQUENCE = [
    "#1B4332", "#2D6A4F", "#40916C", "#52B788",
    "#74C69D", "#95D5B2", "#B7E4C7", "#D8F3DC",
]

PLOTLY_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1B4332", family="sans-serif", size=13),
    margin=dict(l=40, r=20, t=40, b=40),
    xaxis=dict(gridcolor="#E0EDE5", linecolor="#E0EDE5"),
    yaxis=dict(gridcolor="#E0EDE5", linecolor="#E0EDE5"),
    colorway=GREEN_SEQUENCE,
    hoverlabel=dict(bgcolor="#2D6A4F", font_color="white", font_size=13),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)


def apply_chart_style(
    fig,
    height: int = 340,
    xaxis_title: str = "",
    yaxis_title: str = "",
    showlegend: bool | None = None,
):
    """Apply the dashboard green theme to a Plotly figure."""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1B4332", family="sans-serif", size=13),
        margin=dict(l=48, r=20, t=40, b=48),
        hoverlabel=dict(bgcolor="#2D6A4F", font_color="white", font_size=13),
        height=height,
        colorway=GREEN_SEQUENCE,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    if showlegend is not None:
        fig.update_layout(showlegend=showlegend)
    fig.update_xaxes(title_text=xaxis_title, gridcolor="#E0EDE5", linecolor="#E0EDE5")
    fig.update_yaxes(title_text=yaxis_title, gridcolor="#E0EDE5", linecolor="#E0EDE5")
    return fig


def get_css() -> str:
    return """
<style>
/* ============================================================
   GLOBAL
   ============================================================ */
.stApp {
    background-color: #F6FBF7;
}
#MainMenu, footer {visibility: hidden;}

/* ============================================================
   MAIN TITLE
   ============================================================ */
.main-title {
    font-size: 2.2rem;
    font-weight: 800;
    color: #1B4332;
    margin-bottom: 0;
    letter-spacing: -0.5px;
    line-height: 1.2;
}
.sub-title {
    font-size: 0.92rem;
    color: #52796F;
    margin-bottom: 18px;
    font-weight: 400;
}

/* ============================================================
   NAVIGATION TABS
   ============================================================ */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: #FFFFFF;
    padding: 8px 16px;
    border-radius: 14px;
    box-shadow: 0 2px 12px rgba(27, 67, 50, 0.07);
    justify-content: center;
}
.stTabs [data-baseweb="tab"] {
    height: 46px;
    background-color: #EDF7F1;
    border-radius: 10px;
    color: #2D6A4F;
    padding: 0 28px;
    font-weight: 600;
    font-size: 1.0rem;
    border: none;
    white-space: nowrap;
    transition: background 0.2s, color 0.2s;
}
.stTabs [data-baseweb="tab"]:hover {
    background-color: #D8F3DC;
}
.stTabs [aria-selected="true"] {
    background-color: #40916C !important;
    color: #FFFFFF !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    display: none;
}
.stTabs [data-baseweb="tab-border"] {
    display: none;
}

/* ============================================================
   KPI METRIC CARDS
   ============================================================ */
.metric-card {
    background: #FFFFFF;
    padding: 20px 22px;
    border-radius: 14px;
    box-shadow: 0 2px 14px rgba(27, 67, 50, 0.06);
    border-left: 5px solid #40916C;
    margin-bottom: 10px;
    transition: transform 0.15s, box-shadow 0.15s;
}
.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(27, 67, 50, 0.1);
}
.metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: #1B4332;
    line-height: 1.15;
}
.metric-label {
    font-size: 0.85rem;
    color: #52796F;
    margin-top: 4px;
    font-weight: 500;
}
.metric-delta {
    font-size: 0.78rem;
    margin-top: 6px;
    font-weight: 600;
}
.metric-delta.positive { color: #2D6A4F; }
.metric-delta.negative { color: #D64045; }

/* ============================================================
   CONTENT CARDS
   ============================================================ */
.content-card {
    background: #FFFFFF;
    padding: 26px 28px;
    border-radius: 16px;
    box-shadow: 0 2px 16px rgba(27, 67, 50, 0.06);
    margin-top: 14px;
    margin-bottom: 14px;
}
.section-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: #1B4332;
    margin-bottom: 6px;
}
.section-desc {
    font-size: 0.85rem;
    color: #8FA9A0;
    margin-bottom: 16px;
}

/* ============================================================
   PAGE HEADER
   ============================================================ */
.page-header {
    font-size: 1.55rem;
    font-weight: 700;
    color: #1B4332;
    margin-bottom: 4px;
}
.page-desc {
    font-size: 0.88rem;
    color: #52796F;
    margin-bottom: 20px;
}

/* ============================================================
   FILTER BAR
   ============================================================ */
.filter-bar {
    background: #FFFFFF;
    padding: 18px 22px;
    border-radius: 14px;
    box-shadow: 0 2px 10px rgba(27, 67, 50, 0.05);
    margin-bottom: 16px;
    border: 1px solid #E0EDE5;
}
.filter-label {
    font-size: 0.8rem;
    color: #52796F;
    font-weight: 600;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ============================================================
   SIDEBAR
   ============================================================ */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E0EDE5;
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #1B4332;
    font-size: 1.05rem;
    font-weight: 700;
}

/* ============================================================
   STATUS / CONSTRAINT BADGES
   ============================================================ */
.constraint-panel {
    background: #FFFFFF;
    padding: 22px 24px;
    border-radius: 14px;
    box-shadow: 0 2px 14px rgba(27, 67, 50, 0.06);
}
.constraint-row {
    display: flex;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #F0F5F2;
    gap: 12px;
}
.constraint-row:last-child {
    border-bottom: none;
}
.status-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.status-dot.pass { background-color: #2D6A4F; }
.status-dot.warning { background-color: #E9A820; }
.status-dot.violation { background-color: #D64045; }
.constraint-label {
    font-weight: 600;
    color: #1B4332;
    font-size: 0.9rem;
    flex: 1;
}
.constraint-detail {
    font-size: 0.82rem;
    color: #8FA9A0;
}
.status-tag {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}
.status-tag.pass { background: #D8F3DC; color: #1B4332; }
.status-tag.warning { background: #FFF3CD; color: #856404; }
.status-tag.violation { background: #F8D7DA; color: #842029; }

/* ============================================================
   COMPARISON CARDS
   ============================================================ */
.comparison-wrapper {
    display: flex;
    gap: 16px;
    margin: 12px 0;
}
.comparison-card {
    flex: 1;
    background: #FFFFFF;
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(27, 67, 50, 0.06);
    text-align: center;
}
.comparison-card.before {
    border-top: 4px solid #8FA9A0;
}
.comparison-card.after {
    border-top: 4px solid #40916C;
}
.comparison-label {
    font-size: 0.8rem;
    color: #52796F;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.comparison-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #1B4332;
    margin: 6px 0;
}
.comparison-sub {
    font-size: 0.82rem;
    color: #8FA9A0;
}

/* ============================================================
   TABLES / DATAFRAMES
   ============================================================ */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}
div[data-testid="stDataFrame"] > div {
    border-radius: 12px;
    border: 1px solid #E0EDE5;
}

/* ============================================================
   SELECTBOX / MULTISELECT / RADIO
   ============================================================ */
div[data-baseweb="select"] > div {
    border-color: #E0EDE5 !important;
    border-radius: 10px !important;
    background-color: #FFFFFF !important;
}
div[data-baseweb="select"] > div:focus-within {
    border-color: #40916C !important;
    box-shadow: 0 0 0 1px #40916C !important;
}

/* ============================================================
   BUTTONS
   ============================================================ */
.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.2s;
    border: 1px solid #E0EDE5;
}
.stButton > button[kind="primary"] {
    background-color: #40916C;
    color: white;
    border-color: #40916C;
}
.stButton > button[kind="primary"]:hover {
    background-color: #2D6A4F;
    border-color: #2D6A4F;
}

/* ============================================================
   EXPANDERS
   ============================================================ */
.streamlit-expanderHeader {
    font-weight: 600;
    color: #1B4332;
    background: #F6FBF7;
    border-radius: 10px;
}

/* ============================================================
   MAP CONTAINER
   ============================================================ */
.map-container {
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 14px rgba(27, 67, 50, 0.06);
    border: 1px solid #E0EDE5;
    margin: 10px 0;
}

/* ============================================================
   MODE TOGGLE (Planning page)
   ============================================================ */
.mode-toggle {
    background: #FFFFFF;
    padding: 16px 22px;
    border-radius: 14px;
    box-shadow: 0 2px 12px rgba(27, 67, 50, 0.06);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.mode-label {
    font-weight: 600;
    color: #1B4332;
    font-size: 0.95rem;
}

/* ============================================================
   DIVIDER
   ============================================================ */
.custom-divider {
    border: none;
    border-top: 1px solid #E0EDE5;
    margin: 20px 0;
}

/* ============================================================
   PILLS / TAGS
   ============================================================ */
.tag {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    margin: 2px 4px;
    background: #EDF7F1;
    color: #2D6A4F;
}
.tag.active {
    background: #40916C;
    color: #FFFFFF;
}

/* ============================================================
   SCROLLABLE TABLE CONTAINER
   ============================================================ */
.table-container {
    max-height: 480px;
    overflow-y: auto;
    border-radius: 12px;
    border: 1px solid #E0EDE5;
}

/* ============================================================
   TOOLTIP STYLE
   ============================================================ */
.info-tip {
    font-size: 0.78rem;
    color: #8FA9A0;
    font-style: italic;
    margin-top: 4px;
}
</style>
"""
