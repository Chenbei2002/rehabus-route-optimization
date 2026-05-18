"""Page 0 - 旧数据预览: historical route browsing with map and table."""

from __future__ import annotations

import os
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from streamlit_folium import st_folium

from utils.formatters import page_header, section_start, section_end

# ------------------------------------------------------------------
# Easy-to-edit constants (path + field mapping)
# ------------------------------------------------------------------


BASE_DIR = Path(__file__).resolve().parents[2]  # Capstone_code
OLD_DATA_CANDIDATE_PATHS = [
    BASE_DIR / "output_data" / "old_passenger_data.csv",
]

FIELD_MAP = {
    "route_id": "existing_route",
    "passenger": "passenger",
    "board_time": "board_time_str",
    "board_time_minutes": "board_time_minutes",
    "board_stop": "board_stop",
    "board_lat": "board_lat",
    "board_lng": "board_lng",
    "alight_stop": "alight_stop",
    "alight_time_str": "alight_time_str",
    "alight_time_minutes": "alight_time_minutes",
    "trip_duration_minutes_est": "trip_duration_minutes_est",
    "passenger_type": "passenger_type",
    "disability_type": "disability_type",
    "purpose": "purpose",
    "is_wheelchair": "is_wheelchair",
}

REQUIRED_FIELDS = [
    "route_id",
    "passenger",
    "board_lat",
    "board_lng",
]

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_TILE_URL_TEMPLATE = "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&key=__API_KEY__"
ENV_CANDIDATE_PATHS = [
    BASE_DIR / "Streamlit" / ".env",
]


@st.cache_data
def _load_old_data() -> tuple[pd.DataFrame | None, Path | None]:
    """Load historical route data from configured candidate paths."""
    for path in OLD_DATA_CANDIDATE_PATHS:
        if path.exists():
            if path.suffix.lower() == ".csv":
                return pd.read_csv(path), path
            if path.suffix.lower() in {".xlsx", ".xls"}:
                return pd.read_excel(path), path
    return None, None


def _missing_required_fields(df: pd.DataFrame) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_FIELDS:
        col = FIELD_MAP[key]
        if col not in df.columns:
            missing.append(col)
    return missing


def _resolve_column(df: pd.DataFrame, logical_key: str, candidates: list[str]) -> str | None:
    """Return the first available column from candidates."""
    preferred = FIELD_MAP.get(logical_key)
    ordered = [preferred] + [c for c in candidates if c != preferred]
    for col in ordered:
        if col and col in df.columns:
            return col
    return None


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode Google encoded polyline into (lat, lng) tuples."""
    points: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        points.append((lat / 1e5, lng / 1e5))
    return points


def _get_google_maps_key() -> str | None:
    """Read Google Maps key from env or Streamlit secrets."""
    env_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if env_key:
        return env_key

    # Fallback: read .env files directly (Streamlit does not auto-load .env by default).
    for env_path in ENV_CANDIDATE_PATHS:
        if env_path.exists():
            file_key = _read_key_from_env_file(env_path, "GOOGLE_MAPS_API_KEY")
            if file_key:
                return file_key

    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY")
    except Exception:
        return None


def _read_key_from_env_file(env_path: Path, target_key: str) -> str | None:
    """Parse a .env file and return target_key value if present."""
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            k, v = line.split("=", 1)
            if k.strip() != target_key:
                continue
            # Support "KEY = value" and inline comments.
            value = v.split("#", 1)[0].strip().strip('"').strip("'")
            return value or None
    except Exception:
        return None
    return None


@st.cache_data(show_spinner=False)
def _fetch_google_segment_path(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    api_key: str,
) -> list[tuple[float, float]] | None:
    """Fetch drivable path between two points from Google Directions API."""
    try:
        params = {
            "origin": f"{origin_lat},{origin_lng}",
            "destination": f"{dest_lat},{dest_lng}",
            "mode": "driving",
            "key": api_key,
        }
        resp = requests.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        routes = payload.get("routes", [])
        if not routes:
            return None
        polyline = routes[0].get("overview_polyline", {}).get("points")
        if not polyline:
            return None
        return _decode_polyline(polyline)
    except Exception:
        return None


def render_old_data_preview() -> None:
    st.markdown(
        page_header("舊路線預覽", "瀏覽歷史路線（old data）、軌跡與乘客上車明細"),
        unsafe_allow_html=True,
    )

    df, path = _load_old_data()
    if df is None or path is None:
        st.warning(
            "未找到歷史路線資料檔案。請確認以下路徑之一存在："
            "`output_data/old_passenger_data.csv`、"
            "`output_data/passenger_input_part.csv`、"
            "`output_data/passenger_input_clean_2.csv`。"
        )
        return

    missing_fields = _missing_required_fields(df)
    if missing_fields:
        st.error(
            "歷史路線資料缺少必要欄位："
            + ", ".join(missing_fields)
            + "。請檢查 `FIELD_MAP` 或資料檔案欄位名。"
        )
        return

    route_col = _resolve_column(df, "route_id", ["existing_route", "route_id", "route"])
    passenger_col = _resolve_column(df, "passenger", ["passenger"])
    board_time_col = _resolve_column(df, "board_time", ["board_time_str", "board_time"])
    board_time_min_col = _resolve_column(df, "board_time_minutes", ["board_time_minutes"])
    board_stop_col = _resolve_column(df, "board_stop", ["board_stop", "board_location", "board_address"])
    alight_stop_col = _resolve_column(df, "alight_stop", ["alight_stop", "dropoff_stop", "alight_location"])
    alight_time_min_col = _resolve_column(df, "alight_time_minutes", ["alight_time_minutes"])
    board_lat_col = _resolve_column(df, "board_lat", ["board_lat", "pickup_lat"])
    board_lng_col = _resolve_column(df, "board_lng", ["board_lng", "pickup_lng", "board_lon", "pickup_lon"])
    passenger_type_col = _resolve_column(df, "passenger_type", ["passenger_type"])
    wheelchair_col = _resolve_column(df, "is_wheelchair", ["is_wheelchair"])

    unresolved = [
        name for name, value in {
            "route_id": route_col,
            "passenger": passenger_col,
            "board_time(board_time_str preferred)": board_time_col,
            "board_lat": board_lat_col,
            "board_lng": board_lng_col,
        }.items() if value is None
    ]
    if unresolved:
        st.error("無法識別以下關鍵欄位，請檢查 `FIELD_MAP`： " + ", ".join(unresolved))
        return

    route_options = sorted(df[route_col].dropna().astype(str).unique().tolist())
    if not route_options:
        st.info("歷史路線資料中沒有可用的 route_id。")
        return

    selected_route = st.selectbox(
        "選擇歷史路線",
        options=route_options,
        key="old_data_route_id",
    )

    route_df = df[df[route_col].astype(str) == str(selected_route)].copy()
    if route_df.empty:
        st.info("所選路線沒有資料。")
        return

    sort_col = board_time_min_col if board_time_min_col else board_time_col
    route_df = route_df.sort_values(sort_col, na_position="last")

    left, right = st.columns([1, 4])
    with left:
        st.markdown(section_start("路線資訊"), unsafe_allow_html=True)
        st.metric("當前路線 ID", str(selected_route))
        st.metric("當前路線乘客數", route_df[passenger_col].nunique())
        st.markdown(section_end(), unsafe_allow_html=True)

    with right:
        st.markdown(
            section_start("路線地圖", "軌跡線 + 上車點；懸停可查看 passenger 與 board_time"),
            unsafe_allow_html=True,
        )
        google_key = _get_google_maps_key()
        use_google_route = st.toggle(
            "使用 Google 實際道路路線",
            value=bool(google_key),
            help="需要配置 GOOGLE_MAPS_API_KEY。未配置或請求失敗時會自動回退為直線。",
        )
        _render_route_map(
            route_df=route_df,
            passenger_col=passenger_col,
            board_time_col=board_time_col,
            board_stop_col=board_stop_col,
            alight_stop_col=alight_stop_col,
            board_lat_col=board_lat_col,
            board_lng_col=board_lng_col,
            use_google_route=use_google_route and bool(google_key),
            google_maps_key=google_key,
        )
        if use_google_route and not google_key:
            st.info("未檢測到 `GOOGLE_MAPS_API_KEY`，已使用直線連線展示。")
        st.markdown(section_end(), unsafe_allow_html=True)

    st.markdown(
        section_start("🧭 路線時間軸（調度視覺化）", "展示單條路線的上車、行駛、下車全過程"),
        unsafe_allow_html=True,
    )
    render_route_timeline(
        route_df=route_df,
        passenger_col=passenger_col,
        board_time_min_col=board_time_min_col,
        alight_time_min_col=alight_time_min_col,
        board_stop_col=board_stop_col,
        alight_stop_col=alight_stop_col,
        passenger_type_col=passenger_type_col,
        wheelchair_col=wheelchair_col,
    )
    st.markdown(section_end(), unsafe_allow_html=True)

    st.markdown(
        section_start("乘客上車時間明細", "按上車時間排序（優先 board_time_minutes）"),
        unsafe_allow_html=True,
    )
    _render_passenger_table(
        route_df=route_df,
        passenger_col=passenger_col,
        board_time_col=board_time_col,
        board_stop_col=board_stop_col,
        board_lat_col=board_lat_col,
        board_lng_col=board_lng_col,
    )
    st.markdown(section_end(), unsafe_allow_html=True)


def _minutes_to_datetime(minutes: float | int | None) -> pd.Timestamp:
    base_time = pd.Timestamp("2024-01-01 00:00:00")
    minutes_value = 0 if pd.isna(minutes) else float(minutes)
    return base_time + pd.to_timedelta(minutes_value, unit="m")


def _format_clock(minutes: float | int | None) -> str:
    if pd.isna(minutes):
        return "-"
    total_minutes = int(float(minutes))
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _resolve_wc_label(row: pd.Series, passenger_type_col: str | None, wheelchair_col: str | None) -> str:
    if passenger_type_col and passenger_type_col in row.index and pd.notna(row[passenger_type_col]):
        return str(row[passenger_type_col])
    if wheelchair_col and wheelchair_col in row.index:
        return "WC" if pd.to_numeric(row[wheelchair_col], errors="coerce") == 1 else "NWC"
    return "-"


def render_route_timeline(
    route_df: pd.DataFrame,
    passenger_col: str,
    board_time_min_col: str | None,
    alight_time_min_col: str | None,
    board_stop_col: str | None,
    alight_stop_col: str | None,
    passenger_type_col: str | None = None,
    wheelchair_col: str | None = None,
    loading_minutes: int = 5,
    unloading_minutes: int = 5,
) -> None:
    st.subheader("🧭 路線時間軸（調度視覺化）")

    missing = []
    if passenger_col is None:
        missing.append("passenger")
    if board_time_min_col is None:
        missing.append("board_time_minutes")
    if alight_time_min_col is None:
        missing.append("alight_time_minutes")

    if missing:
        st.warning("缺少時間軸所需欄位：`" + "`、`".join(missing) + "`。")
        return

    timeline_source = route_df.copy()
    timeline_source[board_time_min_col] = pd.to_numeric(timeline_source[board_time_min_col], errors="coerce")
    timeline_source[alight_time_min_col] = pd.to_numeric(timeline_source[alight_time_min_col], errors="coerce")
    timeline_source = timeline_source.dropna(subset=[board_time_min_col, alight_time_min_col])

    if timeline_source.empty:
        st.info("當前路線缺少可解析的上下車分鐘欄位，無法繪製時間軸。")
        return

    event_rows: list[dict] = []
    for _, row in timeline_source.iterrows():
        passenger = str(row.get(passenger_col, "-"))
        board_time = float(row[board_time_min_col])
        alight_time = float(row[alight_time_min_col])
        travel_start = board_time + loading_minutes
        travel_end = max(alight_time, travel_start)
        board_stop = row.get(board_stop_col, "-") if board_stop_col else "-"
        alight_stop = row.get(alight_stop_col, "-") if alight_stop_col else "-"
        passenger_type = _resolve_wc_label(row, passenger_type_col, wheelchair_col)
        passenger_track = f"{passenger} ({passenger_type})" if passenger_type != "-" else passenger

        event_rows.extend(
            [
                {
                    "event_type": "Loading",
                    "start_time": _minutes_to_datetime(board_time),
                    "end_time": _minutes_to_datetime(board_time + loading_minutes),
                    "passenger_track": passenger_track,
                    "passenger": passenger,
                    "passenger_type": passenger_type,
                    "stop": board_stop,
                    "time_range": f"{_format_clock(board_time)} - {_format_clock(board_time + loading_minutes)}",
                },
                {
                    "event_type": "Travel",
                    "start_time": _minutes_to_datetime(travel_start),
                    "end_time": _minutes_to_datetime(travel_end),
                    "passenger_track": passenger_track,
                    "passenger": passenger,
                    "passenger_type": passenger_type,
                    "stop": f"{board_stop} → {alight_stop}",
                    "time_range": f"{_format_clock(travel_start)} - {_format_clock(travel_end)}",
                },
                {
                    "event_type": "Unloading",
                    "start_time": _minutes_to_datetime(alight_time),
                    "end_time": _minutes_to_datetime(alight_time + unloading_minutes),
                    "passenger_track": passenger_track,
                    "passenger": passenger,
                    "passenger_type": passenger_type,
                    "stop": alight_stop,
                    "time_range": f"{_format_clock(alight_time)} - {_format_clock(alight_time + unloading_minutes)}",
                },
            ]
        )

    timeline_df = pd.DataFrame(event_rows).sort_values(["start_time", "passenger", "event_type"])
    if timeline_df.empty:
        st.info("當前路線暫無可展示的時間軸事件。")
        return

    passenger_order = (
        timeline_df.groupby("passenger_track")["start_time"]
        .min()
        .sort_values()
        .index
        .tolist()
    )

    fig = px.timeline(
        timeline_df,
        x_start="start_time",
        x_end="end_time",
        y="passenger_track",
        color="event_type",
        color_discrete_map={
            "Loading": "#3B82F6",
            "Travel": "#F59E0B",
            "Unloading": "#22C55E",
        },
        hover_data={
            "passenger": True,
            "passenger_type": True,
            "stop": True,
            "time_range": True,
            "start_time": False,
            "end_time": False,
            "passenger_track": False,
        },
    )
    fig.update_yaxes(categoryorder="array", categoryarray=passenger_order, autorange="reversed")
    fig.update_layout(
        height=max(360, 80 + len(passenger_order) * 42),
        xaxis_title="時間",
        yaxis_title="乘客軌道",
        legend_title="事件類型",
        margin=dict(l=40, r=20, t=30, b=40),
    )
    fig.update_xaxes(tickformat="%H:%M")
    fig.update_traces(
        marker_line_color="rgba(0,0,0,0.15)",
        marker_line_width=1,
        hovertemplate=(
            "乘客: %{customdata[0]}<br>"
            "類型: %{customdata[1]}<br>"
            "事件: %{fullData.name}<br>"
            "站點: %{customdata[2]}<br>"
            "時間: %{customdata[3]}<extra></extra>"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("說明：Loading / Unloading 在舊資料中按 5 分鐘估算，可在 `render_route_timeline()` 參數中調整。")


def _render_route_map(
    route_df: pd.DataFrame,
    passenger_col: str,
    board_time_col: str,
    board_stop_col: str,
    alight_stop_col: str | None,
    board_lat_col: str,
    board_lng_col: str,
    use_google_route: bool,
    google_maps_key: str | None,
) -> None:
    map_df = route_df.dropna(subset=[board_lat_col, board_lng_col]).copy()
    if map_df.empty:
        st.info("該路線沒有可用座標，無法繪製地圖。")
        return

    map_df[board_lat_col] = pd.to_numeric(map_df[board_lat_col], errors="coerce")
    map_df[board_lng_col] = pd.to_numeric(map_df[board_lng_col], errors="coerce")
    map_df = map_df.dropna(subset=[board_lat_col, board_lng_col])
    if map_df.empty:
        st.info("該路線座標欄位無法解析為數值。")
        return

    map_center = [map_df[board_lat_col].mean(), map_df[board_lng_col].mean()]
    if use_google_route and google_maps_key:
        m = folium.Map(location=map_center, zoom_start=12, tiles=None)
        folium.TileLayer(
            tiles=GOOGLE_TILE_URL_TEMPLATE.replace("__API_KEY__", google_maps_key),
            attr="Google",
            name="Google Roadmap",
            overlay=False,
            control=False,
        ).add_to(m)
    else:
        m = folium.Map(location=map_center, zoom_start=12, tiles="cartodbpositron")

    coords = list(zip(map_df[board_lat_col], map_df[board_lng_col]))
    if len(coords) >= 2:
        if use_google_route and google_maps_key:
            full_path: list[tuple[float, float]] = []
            for i in range(len(coords) - 1):
                (o_lat, o_lng), (d_lat, d_lng) = coords[i], coords[i + 1]
                segment = _fetch_google_segment_path(o_lat, o_lng, d_lat, d_lng, google_maps_key)
                if segment:
                    if full_path and segment and full_path[-1] == segment[0]:
                        full_path.extend(segment[1:])
                    else:
                        full_path.extend(segment)
                else:
                    # Fallback to direct line segment if API fails on a leg.
                    full_path.extend([(o_lat, o_lng), (d_lat, d_lng)])
            path_to_draw = full_path if full_path else coords
        else:
            path_to_draw = coords

        folium.PolyLine(
            path_to_draw,
            color="#2D6A4F",
            weight=4,
            opacity=0.8,
            tooltip="路線軌跡",
        ).add_to(m)

    for _, row in map_df.iterrows():
        passenger = row.get(passenger_col, "-")
        board_time = row.get(board_time_col, "-")
        board_stop = row.get(board_stop_col, "-") if board_stop_col in map_df.columns else "-"
        alight_stop = (
            row.get(alight_stop_col, "-")
            if (alight_stop_col is not None and alight_stop_col in map_df.columns)
            else "-"
        )
        tooltip = f"passenger: {passenger}<br>board_time: {board_time}<br>alight_stop: {alight_stop}"
        popup = (
            f"<b>passenger</b>: {passenger}<br>"
            f"<b>board_time</b>: {board_time}<br>"
            f"<b>board_stop</b>: {board_stop}<br>"
            f"<b>alight_stop</b>: {alight_stop}"
        )
        folium.CircleMarker(
            location=[row[board_lat_col], row[board_lng_col]],
            radius=5,
            color="#1B4332",
            fill=True,
            fill_color="#2D6A4F",
            fill_opacity=0.85,
            tooltip=tooltip,
            popup=popup,
        ).add_to(m)

    st_folium(m, use_container_width=True, height=500, returned_objects=[])


def _render_passenger_table(
    route_df: pd.DataFrame,
    passenger_col: str,
    board_time_col: str,
    board_stop_col: str,
    board_lat_col: str,
    board_lng_col: str,
) -> None:
    fixed_columns = [
        ("passenger", passenger_col),
        ("passenger_type", "passenger_type"),
        ("disability_type", "disability_type"),
        ("purpose", "purpose"),
        ("board_stop", board_stop_col),
        ("board_time_str", "board_time_str"),
        ("alight_stop", "alight_stop"),
        ("alight_time_str", "alight_time_str"),
        ("trip_duration_minutes_est", "trip_duration_minutes_est"),
        ("board_lat", board_lat_col),
        ("board_lng", board_lng_col),
    ]

    # Fixed display order with Chinese column names; missing fields show "-" for stable layout.
    table_df = pd.DataFrame()
    for out_col, src_col in fixed_columns:
        if src_col and src_col in route_df.columns:
            table_df[out_col] = route_df[src_col]
        else:
            table_df[out_col] = "-"

    # If board_time_str is absent, fill the column from resolved time source.
    if (table_df["board_time_str"] == "-").all() and board_time_col in route_df.columns:
        table_df["board_time_str"] = route_df[board_time_col]

    st.dataframe(
        table_df,
        use_container_width=True,
        height=320,
        column_config={
            "passenger": "乘客",
            "passenger_type": "乘客類型",
            "disability_type": "殘障類型",
            "purpose": "用途",
            "board_stop": "上車地點",
            "board_time_str": "上車時間",
            "alight_stop": "下車地點",
            "alight_time_str": "下車時間",
            "trip_duration_minutes_est": st.column_config.NumberColumn(
                "預計行程時長(分鐘)",
                format="%.0f",
            ),
        },
    )
