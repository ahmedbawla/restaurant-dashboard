"""
Reusable KPI card rendered via st.metric + custom HTML for extra styling.
"""

import streamlit as st


def kpi_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
) -> None:
    """
    Renders a styled KPI metric card.

    Parameters
    ----------
    label       : Display label (e.g. "Daily Revenue")
    value       : Formatted value string (e.g. "$18,450")
    delta       : Optional change indicator (e.g. "+4.2% vs yesterday")
    delta_color : "normal" | "inverse" | "off"
    help_text   : Tooltip text
    """
    st.metric(
        label=label,
        value=value,
        delta=delta,
        delta_color=delta_color,
        help=help_text,
    )


def threshold_badge(value: float, target: float, warning: float, unit: str = "%") -> str:
    """
    Returns a colored emoji badge based on threshold comparison.
    Green = at/below target, Yellow = warning zone, Red = above warning.
    """
    if value <= target:
        return f"🟢 {value:.1f}{unit}"
    elif value <= warning:
        return f"🟡 {value:.1f}{unit}"
    else:
        return f"🔴 {value:.1f}{unit}"


def format_currency(amount: float) -> str:
    return f"${amount:,.0f}"


def format_pct(value: float) -> str:
    return f"{value:.1f}%"
