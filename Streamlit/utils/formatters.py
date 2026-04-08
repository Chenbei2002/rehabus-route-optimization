"""HTML helper functions for dashboard components."""

from __future__ import annotations


def metric_card(value: str | int | float, label: str, delta: str | None = None, delta_positive: bool = True) -> str:
    delta_html = ""
    if delta is not None:
        cls = "positive" if delta_positive else "negative"
        arrow = "▲" if delta_positive else "▼"
        delta_html = f'<div class="metric-delta {cls}">{arrow} {delta}</div>'
    return f"""
    <div class="metric-card">
        <div class="metric-value">{value}</div>
        <div class="metric-label">{label}</div>
        {delta_html}
    </div>"""


def section_start(title: str, description: str | None = None) -> str:
    desc = f'<div class="section-desc">{description}</div>' if description else ""
    return f"""<div class="content-card"><div class="section-title">{title}</div>{desc}"""


def section_end() -> str:
    return "</div>"


def page_header(title: str, description: str | None = None) -> str:
    desc = f'<div class="page-desc">{description}</div>' if description else ""
    return f'<div class="page-header">{title}</div>{desc}'


def constraint_row(label: str, status: str, detail: str = "") -> str:
    """status: 'pass' | 'warning' | 'violation'"""
    return f"""
    <div class="constraint-row">
        <span class="status-dot {status}"></span>
        <span class="constraint-label">{label}</span>
        <span class="constraint-detail">{detail}</span>
    </div>"""


def status_tag(label: str, status: str) -> str:
    """Small inline tag. status: 'pass' | 'warning' | 'violation'"""
    return f'<span class="status-tag {status}">{label}</span>'


def comparison_pair(label_before: str, val_before, label_after: str, val_after, sub_before: str = "", sub_after: str = "") -> str:
    sub_b = f'<div class="comparison-sub">{sub_before}</div>' if sub_before else ""
    sub_a = f'<div class="comparison-sub">{sub_after}</div>' if sub_after else ""
    return f"""
    <div class="comparison-wrapper">
        <div class="comparison-card before">
            <div class="comparison-label">{label_before}</div>
            <div class="comparison-value">{val_before}</div>
            {sub_b}
        </div>
        <div class="comparison-card after">
            <div class="comparison-label">{label_after}</div>
            <div class="comparison-value">{val_after}</div>
            {sub_a}
        </div>
    </div>"""


def filter_bar_start() -> str:
    return '<div class="filter-bar">'


def filter_bar_end() -> str:
    return "</div>"
