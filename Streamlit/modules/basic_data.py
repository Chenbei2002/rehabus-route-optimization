"""Page 1 – 基础数据: single-page interactive analysis dashboard."""

from __future__ import annotations

import ast

import pandas as pd
import plotly.express as px
import streamlit as st
from plotly.colors import qualitative

from utils.formatters import page_header
from utils.styles import GREEN_SEQUENCE, apply_chart_style

FIELD_MAP = {
    "route_id": ["route_id", "existing_route", "route"],
    "passenger_id": ["passenger_id", "passenger", "customer_id"],
    "passenger_type": ["passenger_type"],
    "wheelchair": ["is_wheelchair"],
    "purpose": ["purpose"],
    "day_list": ["day_list", "day_pattern"],
    "disability_type": ["disability_type"],
    "board_district": ["board_district"],
    "alight_district": ["alight_district"],
    "board_stop": ["board_stop", "board_location", "board_address"],
    "alight_stop": ["alight_stop", "dropoff_stop", "alight_location"],
    "board_time_minutes": ["board_time_minutes"],
    "alight_time_minutes": ["alight_time_minutes"],
    "trip_duration_minutes_est": ["trip_duration_minutes_est"],
    "board_lat": ["board_lat", "pickup_lat"],
    "board_lng": ["board_lng", "board_lon", "pickup_lng", "pickup_lon", "lng", "lon"],
    "alight_lat": ["alight_lat", "dropoff_lat"],
    "alight_lng": ["alight_lng", "alight_lon", "dropoff_lng", "dropoff_lon"],
}

FIELD_LABELS = {
    "route_id": "路線 ID",
    "passenger_id": "乘客 ID",
    "passenger_type": "乘客類型",
    "wheelchair": "輪椅標記",
    "purpose": "用途",
    "day_list": "服務日列表",
    "disability_type": "殘障類型",
    "board_district": "上車區域",
    "alight_district": "下車區域",
    "board_stop": "上車站點",
    "alight_stop": "下車站點",
    "board_time_minutes": "上車時間（分鐘）",
    "alight_time_minutes": "下車時間（分鐘）",
    "trip_duration_minutes_est": "預計車程（分鐘）",
    "board_lat": "上車緯度",
    "board_lng": "上車經度",
    "alight_lat": "下車緯度",
    "alight_lng": "下車經度",
}

ALL_OPTION = "全部"
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_PATTERN_MAP = {
    "1": "Mon",
    "2": "Tue",
    "3": "Wed",
    "4": "Thu",
    "5": "Fri",
    "6": "Sat",
    "7": "Sun",
}
TIME_GRAIN_OPTIONS = {
    "按小時": 60,
    "按30分鐘": 30,
    "按10分鐘": 10,
}


def render_basic_data(filtered_df: pd.DataFrame, full_df: pd.DataFrame) -> None:
    st.markdown(
        page_header("基礎資料", "單頁面、可互動的分析 dashboard"),
        unsafe_allow_html=True,
    )

    source_df = filtered_df.copy()
    option_df = full_df.copy() if not full_df.empty else source_df.copy()

    if source_df.empty:
        st.warning("當前資料為空，無法展示基礎分析頁面。")
        return

    district_color_map = build_district_color_map(option_df)
    filters = render_global_filters(option_df, source_df)
    filtered_page_df = apply_filters(source_df, filters)

    st.caption(f"當前篩選結果：{len(filtered_page_df):,} 條記錄")
    if filtered_page_df.empty:
        st.warning("當前篩選條件下無資料，請調整篩選條件。")
        return

    render_overview(filtered_page_df)
    st.divider()
    render_route_capacity(filtered_page_df)
    st.divider()
    render_passenger_profile(filtered_page_df)
    st.divider()
    render_spatial_analysis(filtered_page_df, district_color_map)
    st.divider()
    render_time_analysis(filtered_page_df)


def render_global_filters(option_df: pd.DataFrame, current_df: pd.DataFrame) -> dict:
    st.subheader("全域篩選")
    st.caption("以下篩選會聯動影響本頁所有模組。")
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: #F1F6EC;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    route_col = _resolve_field(option_df, "route_id")
    passenger_type_col = _resolve_field(option_df, "passenger_type")
    purpose_col = _resolve_field(option_df, "purpose")
    day_list_col = _resolve_field(option_df, "day_list")
    board_district_col = _resolve_field(option_df, "board_district")
    alight_district_col = _resolve_field(option_df, "alight_district")
    board_time_col = _resolve_field(option_df, "board_time_minutes")

    unavailable: list[str] = []
    if route_col is None:
        unavailable.append("route_id")
    if passenger_type_col is None:
        unavailable.append("passenger_type")
    if purpose_col is None:
        unavailable.append("purpose")
    if day_list_col is None:
        unavailable.append("day_list")
    if board_district_col is None and alight_district_col is None:
        unavailable.append("district")
    if board_time_col is None:
        unavailable.append("board_time_minutes")

    if unavailable:
        labels = ", ".join(f"`{name}`" for name in unavailable)
        st.info(f"當前資料缺少以下篩選欄位，已自動跳過：{labels}")

    with st.container(border=True):
        st.markdown("**篩選面板**")
        c1, c2, c3 = st.columns(3)
        c4, c5, c6 = st.columns(3)

        with c1:
            route_options = [ALL_OPTION] + _safe_unique_values(option_df, route_col)
            selected_route = st.selectbox("route_id", route_options, index=0, key="basic_route_filter")

        with c2:
            passenger_type_options = ["All"] + _safe_unique_values(option_df, passenger_type_col)
            selected_passenger_type = st.selectbox(
                "passenger_type",
                passenger_type_options,
                index=0,
                key="basic_passenger_type_filter",
            )

        with c3:
            selected_purposes = st.multiselect(
                "purpose",
                _safe_unique_values(option_df, purpose_col),
                default=[],
                key="basic_purpose_filter",
                placeholder="不選擇則為全部",
            )

        with c4:
            selected_day_patterns = st.multiselect(
                "day_list（按星期）",
                _build_weekday_options(option_df, day_list_col),
                default=[],
                key="basic_day_pattern_filter",
                placeholder="不選擇則為全部",
            )

        with c5:
            district_options = _build_district_options(option_df, board_district_col, alight_district_col)
            selected_districts = st.multiselect(
                "district",
                district_options,
                default=[],
                key="basic_district_filter",
                placeholder="同時匹配上車 / 下車區域",
            )

        with c6:
            time_range = _build_time_slider(option_df, board_time_col)

        _render_filter_summary(
            route=selected_route,
            passenger_type=selected_passenger_type,
            purposes=selected_purposes,
            day_patterns=selected_day_patterns,
            districts=selected_districts,
            time_range=time_range,
        )

    return {
        "route": selected_route,
        "passenger_type": selected_passenger_type,
        "purposes": selected_purposes,
        "day_patterns": selected_day_patterns,
        "districts": selected_districts,
        "time_range": time_range,
        "field_map": {
            "route_id": _resolve_field(current_df, "route_id"),
            "passenger_type": _resolve_field(current_df, "passenger_type"),
            "purpose": _resolve_field(current_df, "purpose"),
            "day_list": _resolve_field(current_df, "day_list"),
            "board_district": _resolve_field(current_df, "board_district"),
            "alight_district": _resolve_field(current_df, "alight_district"),
            "board_time_minutes": _resolve_field(current_df, "board_time_minutes"),
        },
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered = df.copy()
    field_map = filters["field_map"]

    route_col = field_map["route_id"]
    if route_col and filters["route"] != ALL_OPTION:
        filtered = filtered[filtered[route_col].astype(str) == str(filters["route"])]

    passenger_type_col = field_map["passenger_type"]
    if passenger_type_col and filters["passenger_type"] != "All":
        filtered = filtered[
            filtered[passenger_type_col].astype(str) == str(filters["passenger_type"])
        ]

    purpose_col = field_map["purpose"]
    if purpose_col and filters["purposes"]:
        filtered = filtered[filtered[purpose_col].astype(str).isin(filters["purposes"])]

    day_list_col = field_map["day_list"]
    if day_list_col and filters["day_patterns"]:
        selected_days = set(filters["day_patterns"])
        filtered = filtered[
            filtered[day_list_col]
            .apply(lambda value: bool(set(_parse_day_list(value)) & selected_days))
        ]

    districts = filters["districts"]
    board_district_col = field_map["board_district"]
    alight_district_col = field_map["alight_district"]
    if districts:
        district_mask = pd.Series(False, index=filtered.index)
        if board_district_col:
            district_mask = district_mask | filtered[board_district_col].astype(str).isin(districts)
        if alight_district_col:
            district_mask = district_mask | filtered[alight_district_col].astype(str).isin(districts)
        filtered = filtered[district_mask]

    board_time_col = field_map["board_time_minutes"]
    if board_time_col and filters["time_range"] is not None:
        board_time_series = pd.to_numeric(filtered[board_time_col], errors="coerce")
        start_minute, end_minute = filters["time_range"]
        filtered = filtered[board_time_series.between(start_minute, end_minute, inclusive="both")]

    return filtered


def build_district_color_map(df: pd.DataFrame) -> dict[str, str]:
    board_district_col = _resolve_field(df, "board_district")
    alight_district_col = _resolve_field(df, "alight_district")
    districts = _build_district_options(df, board_district_col, alight_district_col)

    palette = (
        qualitative.Set3
        + qualitative.Safe
        + qualitative.Plotly
        + qualitative.Bold
        + GREEN_SEQUENCE
    )
    return {district: palette[i % len(palette)] for i, district in enumerate(districts)}


def render_overview(df: pd.DataFrame) -> None:
    _module_header("📊 總覽", "核心指標隨全域篩選變化，不增加額外複雜互動。")

    route_col = _resolve_field(df, "route_id")
    passenger_col = _resolve_field(df, "passenger_id")
    wheelchair_col = _resolve_field(df, "wheelchair")

    total_routes = _nunique_or_len(df, route_col)
    total_passengers = _nunique_or_len(df, passenger_col)
    avg_passengers = total_passengers / total_routes if total_routes else 0

    wheelchair_value = "—"
    if wheelchair_col:
        wheelchair_count = pd.to_numeric(df[wheelchair_col], errors="coerce").fillna(0).sum()
        if total_passengers:
            wheelchair_value = f"{wheelchair_count / total_passengers * 100:.1f}%"
    else:
        st.warning(f"缺少欄位：`{FIELD_LABELS['wheelchair']}`，無法計算 wheelchair 佔比。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總路線數", f"{total_routes:,}")
    c2.metric("總乘客數", f"{total_passengers:,}")
    c3.metric("平均每條路線乘客數", f"{avg_passengers:.1f}")
    c4.metric("Wheelchair 佔比", wheelchair_value)


def render_route_capacity(df: pd.DataFrame) -> None:
    _module_header("🚌 路線與容量", "查看每條路線的乘客數量分佈，並查看 Top N 路線。")

    route_col = _resolve_field(df, "route_id")
    passenger_col = _resolve_field(df, "passenger_id")
    wheelchair_col = _resolve_field(df, "wheelchair")

    if route_col is None:
        st.warning(f"缺少欄位：`{FIELD_LABELS['route_id']}`，無法進行路線分析。")
        return

    route_summary = _build_route_summary(df, route_col, passenger_col, wheelchair_col)
    if route_summary.empty:
        st.info("路線與容量模組暫無可展示資料。")
        return

    _, controls_right = st.columns([2, 1])
    with controls_right:
        top_n = st.slider("Top N routes", min_value=5, max_value=30, value=10, key="route_top_n")

    metric_col = "passenger_count"
    metric_label = "乘客數"
    metric_color = GREEN_SEQUENCE[1]

    left, right = st.columns(2)
    with left:
        fig = px.histogram(
            route_summary,
            x=metric_col,
            nbins=min(20, max(5, route_summary[metric_col].nunique())),
            color_discrete_sequence=[metric_color],
        )
        apply_chart_style(fig, xaxis_title=f"每條路線{metric_label}", yaxis_title="路線數")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        top_routes = route_summary.sort_values(metric_col, ascending=False).head(top_n)
        fig = px.bar(
            top_routes,
            x="route_id",
            y=metric_col,
            text=metric_col,
            color_discrete_sequence=[metric_color],
        )
        apply_chart_style(fig, xaxis_title="路線", yaxis_title=metric_label)
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        route_summary.sort_values(metric_col, ascending=False),
        use_container_width=True,
        height=200,
        column_config={
            "route_id": "路線",
            "passenger_count": "乘客總數",
            "wheelchair_count": "攜帶輪椅的乘客數",
            "seated_count": "不攜帶輪椅的乘客數",
        },
    )


def render_passenger_profile(df: pd.DataFrame) -> None:
    _module_header("🧍 乘客結構", "支援在用途、服務日模式、殘障類型之間切換。")

    profile_options = {
        "purpose 分佈": ("purpose", "用途"),
        "day_list 分佈": ("day_list", "服務日列表"),
        "disability_type 分佈": ("disability_type", "殘障類型"),
    }
    selected_profile = st.radio(
        "分析視角",
        list(profile_options.keys()),
        horizontal=True,
        key="profile_view",
    )

    profile_key, profile_label = profile_options[selected_profile]
    profile_col = _resolve_field(df, profile_key)
    if profile_key == "day_list":
        profile_counts = _weekday_distribution(df, profile_col)
    else:
        profile_counts = _value_counts_frame(df, profile_col, "category", "count")

    if profile_counts.empty:
        st.warning(f"缺少欄位：`{FIELD_LABELS[profile_key]}`，無法展示該分佈。")
        return

    fig = px.bar(
        profile_counts,
        x="category",
        y="count",
        text="count",
        color="category",
        color_discrete_sequence=qualitative.Safe + GREEN_SEQUENCE,
    )
    apply_chart_style(fig, xaxis_title=profile_label, yaxis_title="記錄數", showlegend=False)
    fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)


def render_spatial_analysis(df: pd.DataFrame, district_color_map: dict[str, str]) -> None:
    _module_header("🗺️ 空間分佈", "重點模組：支援上車 / 下車 / 同時顯示，並按 district 固定顏色映射。")

    display_mode = st.radio(
        "顯示內容",
        ["上車點", "下車點", "同時顯示"],
        horizontal=True,
        key="spatial_display_mode",
    )

    point_df = _build_spatial_point_frame(df, display_mode)
    if point_df.empty:
        st.warning("空間分佈模組缺少必要欄位或有效座標，無法展示地圖。")
    else:
        left, right = st.columns([2, 1])
        with left:
            fig = px.scatter_mapbox(
                point_df,
                lat="lat",
                lon="lon",
                color="district",
                size="records",
                hover_name="stop",
                hover_data={
                    "district": True,
                    "point_type": True,
                    "records": True,
                    "lat": False,
                    "lon": False,
                },
                zoom=10,
                height=520,
                color_discrete_map=district_color_map,
            )
            fig.update_layout(
                mapbox_style="carto-positron",
                margin=dict(l=0, r=0, t=10, b=10),
                legend_title="District",
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            district_counts = (
                point_df.groupby(["district"], as_index=False)["records"]
                .sum()
                .sort_values("records", ascending=False)
            )
            fig = px.bar(
                district_counts.head(15),
                x="records",
                y="district",
                orientation="h",
                text="records",
                color="district",
                color_discrete_map=district_color_map,
            )
            apply_chart_style(fig, xaxis_title="記錄數", yaxis_title="District", showlegend=False)
            fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True)


def render_time_analysis(df: pd.DataFrame) -> None:
    _module_header("⏱️ 時間分析", "支援切換上車時間、下車時間、行程時長，並調整統計粒度。")

    metric_options = {
        "上車時間": ("board_time_minutes", True, "上車時間"),
        "下車時間": ("alight_time_minutes", True, "下車時間"),
        "行程時長": ("trip_duration_minutes_est", False, "行程時長"),
    }

    left, right = st.columns([2, 1])
    with left:
        selected_metric = st.radio(
            "分析對象",
            list(metric_options.keys()),
            horizontal=True,
            key="time_metric_view",
        )
    with right:
        selected_grain = st.selectbox(
            "統計粒度",
            list(TIME_GRAIN_OPTIONS.keys()),
            index=0,
            key="time_grain_view",
        )

    logical_key, is_clock, axis_label = metric_options[selected_metric]
    series_col = _resolve_field(df, logical_key)
    if series_col is None:
        st.warning(f"缺少欄位：`{FIELD_LABELS[logical_key]}`，無法展示該時間分析。")
        return

    dist_df = _build_time_distribution(
        df=df,
        col=series_col,
        grain_minutes=TIME_GRAIN_OPTIONS[selected_grain],
        is_clock=is_clock,
    )
    if dist_df.empty:
        st.warning("當前時間分析模組沒有可展示的資料。")
        return

    fig = px.bar(
        dist_df,
        x="bucket_label",
        y="count",
        text="count",
        hover_data={"bucket_start": True, "count": True},
        color_discrete_sequence=[GREEN_SEQUENCE[2] if is_clock else GREEN_SEQUENCE[5]],
    )
    apply_chart_style(fig, xaxis_title=axis_label, yaxis_title="記錄數")
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, use_container_width=True)


def _module_header(title: str, description: str) -> None:
    st.subheader(title)
    st.caption(description)


def _resolve_field(df: pd.DataFrame, key: str) -> str | None:
    for candidate in FIELD_MAP.get(key, []):
        if candidate in df.columns:
            return candidate
    return None


def _safe_unique_values(df: pd.DataFrame, col: str | None) -> list[str]:
    if col is None:
        return []
    values = (
        df[col]
        .dropna()
        .astype(str)
        .map(str.strip)
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(values)


def _parse_day_list(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        if pd.isna(value):
            return []
        text = str(value).strip()
        if not text:
            return []

        if all(ch in DAY_PATTERN_MAP for ch in text):
            return [DAY_PATTERN_MAP[ch] for ch in text if ch in DAY_PATTERN_MAP]

        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                raw_items = list(parsed)
            else:
                raw_items = [text]
        except (ValueError, SyntaxError):
            raw_items = [part.strip() for part in text.split(",")]

    normalized: list[str] = []
    for item in raw_items:
        item_text = str(item).strip().strip("'").strip('"')
        if item_text in DAY_ORDER:
            normalized.append(item_text)
            continue
        if all(ch in DAY_PATTERN_MAP for ch in item_text):
            normalized.extend(DAY_PATTERN_MAP[ch] for ch in item_text if ch in DAY_PATTERN_MAP)

    return [day for day in DAY_ORDER if day in normalized]


def _build_weekday_options(df: pd.DataFrame, col: str | None) -> list[str]:
    if col is None:
        return []

    seen_days: set[str] = set()
    for value in df[col].dropna():
        seen_days.update(_parse_day_list(value))
    return [day for day in DAY_ORDER if day in seen_days]


def _build_district_options(
    df: pd.DataFrame,
    board_district_col: str | None,
    alight_district_col: str | None,
) -> list[str]:
    districts: set[str] = set()
    if board_district_col:
        districts.update(_safe_unique_values(df, board_district_col))
    if alight_district_col:
        districts.update(_safe_unique_values(df, alight_district_col))
    return sorted(districts)


def _weekday_distribution(df: pd.DataFrame, col: str | None) -> pd.DataFrame:
    if col is None:
        return pd.DataFrame()

    weekday_series = df[col].apply(_parse_day_list).explode().dropna()
    if weekday_series.empty:
        return pd.DataFrame()

    counts = (
        weekday_series.value_counts()
        .reindex(DAY_ORDER, fill_value=0)
        .rename_axis("category")
        .reset_index(name="count")
    )
    return counts[counts["count"] > 0]


def _build_time_slider(df: pd.DataFrame, board_time_col: str | None) -> tuple[int, int] | None:
    if board_time_col is None:
        st.caption("時間範圍：缺少 `board_time_minutes` 欄位，已跳過。")
        return None

    time_series = pd.to_numeric(df[board_time_col], errors="coerce").dropna()
    if time_series.empty:
        st.caption("時間範圍：當前無可用時間值，已跳過。")
        return None

    min_time = int(time_series.min())
    max_time = int(time_series.max())
    if min_time == max_time:
        st.caption(f"時間範圍固定為 {_format_minutes(min_time)}")
        return (min_time, max_time)

    selected_range = st.slider(
        "board_time_minutes 範圍",
        min_value=min_time,
        max_value=max_time,
        value=(min_time, max_time),
        format="%d",
        key="basic_board_time_range",
    )
    st.caption(
        "已選時間範圍："
        f" `{_format_minutes(selected_range[0])} - {_format_minutes(selected_range[1])}`"
    )
    return selected_range


def _render_filter_summary(
    route: str,
    passenger_type: str,
    purposes: list[str],
    day_patterns: list[str],
    districts: list[str],
    time_range: tuple[int, int] | None,
) -> None:
    summary_parts = [
        f"route: `{route}`" if route != ALL_OPTION else "route: `全部`",
        f"passenger_type: `{passenger_type}`" if passenger_type != "All" else "passenger_type: `All`",
        f"purpose: `{', '.join(purposes)}`" if purposes else "purpose: `全部`",
        f"day_list: `{', '.join(day_patterns)}`" if day_patterns else "day_list: `全部`",
        f"district: `{', '.join(districts)}`" if districts else "district: `全部`",
    ]
    if time_range is not None:
        summary_parts.append(
            f"time: `{_format_minutes(time_range[0])} - {_format_minutes(time_range[1])}`"
        )

    st.caption("當前篩選: " + " | ".join(summary_parts))


def _nunique_or_len(df: pd.DataFrame, col: str | None) -> int:
    if col is None:
        return len(df)
    return int(df[col].nunique(dropna=True))


def _numeric_series(df: pd.DataFrame, col: str | None) -> pd.Series:
    if col is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").dropna()


def _value_counts_frame(
    df: pd.DataFrame,
    col: str | None,
    label_name: str,
    count_name: str,
) -> pd.DataFrame:
    if col is None:
        return pd.DataFrame()
    counts = (
        df[col]
        .fillna("Unknown")
        .astype(str)
        .value_counts()
        .rename_axis(label_name)
        .reset_index(name=count_name)
    )
    return counts


def _build_route_summary(
    df: pd.DataFrame,
    route_col: str,
    passenger_col: str | None,
    wheelchair_col: str | None,
) -> pd.DataFrame:
    grouped = df.groupby(route_col, dropna=False)

    if passenger_col:
        passenger_counts = grouped[passenger_col].nunique(dropna=True)
    else:
        passenger_counts = grouped.size()

    summary = passenger_counts.rename("passenger_count").reset_index()
    summary = summary.rename(columns={route_col: "route_id"})

    if wheelchair_col:
        wheelchair_counts = (
            grouped[wheelchair_col]
            .sum(min_count=1)
            .fillna(0)
            .rename("wheelchair_count")
            .reset_index()
        )
        wheelchair_counts = wheelchair_counts.rename(columns={route_col: "route_id"})
        summary = summary.merge(wheelchair_counts, on="route_id", how="left")
    else:
        summary["wheelchair_count"] = 0
        st.warning(f"缺少欄位：`{FIELD_LABELS['wheelchair']}`，路線座位數按 0 輪椅人數處理。")

    summary["wheelchair_count"] = pd.to_numeric(summary["wheelchair_count"], errors="coerce").fillna(0)
    summary["seated_count"] = (summary["passenger_count"] - summary["wheelchair_count"]).clip(lower=0)
    return summary


def _build_spatial_point_frame(df: pd.DataFrame, display_mode: str) -> pd.DataFrame:
    board_fields = {
        "lat": _resolve_field(df, "board_lat"),
        "lng": _resolve_field(df, "board_lng"),
        "district": _resolve_field(df, "board_district"),
        "stop": _resolve_field(df, "board_stop"),
    }
    alight_fields = {
        "lat": _resolve_field(df, "alight_lat"),
        "lng": _resolve_field(df, "alight_lng"),
        "district": _resolve_field(df, "alight_district"),
        "stop": _resolve_field(df, "alight_stop"),
    }

    point_frames: list[pd.DataFrame] = []
    if display_mode in {"上車點", "同時顯示"}:
        board_df = _make_point_frame(df, board_fields, "Board")
        if not board_df.empty:
            point_frames.append(board_df)
    if display_mode in {"下車點", "同時顯示"}:
        alight_df = _make_point_frame(df, alight_fields, "Alight")
        if not alight_df.empty:
            point_frames.append(alight_df)

    if not point_frames:
        return pd.DataFrame()

    point_df = pd.concat(point_frames, ignore_index=True)
    point_df = (
        point_df.groupby(["lat", "lon", "district", "stop", "point_type"], as_index=False)["records"]
        .sum()
    )
    return point_df


def _make_point_frame(df: pd.DataFrame, fields: dict[str, str | None], point_type: str) -> pd.DataFrame:
    if any(fields[key] is None for key in ("lat", "lng", "district", "stop")):
        return pd.DataFrame()

    point_df = df[[fields["lat"], fields["lng"], fields["district"], fields["stop"]]].copy()
    point_df.columns = ["lat", "lon", "district", "stop"]
    point_df["lat"] = pd.to_numeric(point_df["lat"], errors="coerce")
    point_df["lon"] = pd.to_numeric(point_df["lon"], errors="coerce")
    point_df["district"] = point_df["district"].fillna("Unknown").astype(str)
    point_df["stop"] = point_df["stop"].fillna("Unknown").astype(str)
    point_df = point_df.dropna(subset=["lat", "lon"])
    if point_df.empty:
        return pd.DataFrame()

    point_df["point_type"] = point_type
    point_df["records"] = 1
    return point_df


def _build_time_distribution(
    df: pd.DataFrame,
    col: str,
    grain_minutes: int,
    is_clock: bool,
) -> pd.DataFrame:
    series = _numeric_series(df, col)
    if series.empty:
        return pd.DataFrame()

    bucket_start = (series // grain_minutes).astype(int) * grain_minutes
    dist_df = (
        bucket_start.value_counts()
        .sort_index()
        .rename_axis("bucket_start")
        .reset_index(name="count")
    )

    if is_clock:
        dist_df["bucket_start"] = dist_df["bucket_start"].clip(lower=0, upper=24 * 60)
        dist_df["bucket_label"] = dist_df["bucket_start"].apply(_format_minutes)
    else:
        dist_df["bucket_label"] = dist_df["bucket_start"].apply(
            lambda x: f"{int(x)}-{int(x + grain_minutes)} 分鐘"
        )

    return dist_df


def _format_minutes(minutes: int | float) -> str:
    total_minutes = int(minutes)
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"
