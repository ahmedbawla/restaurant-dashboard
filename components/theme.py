"""
Professional corporate theme for the BI Dashboard.
Call apply_professional_theme() at the top of each page.
"""

import streamlit as st

# Brand palette
NAVY   = "#1B4F72"
GOLD   = "#D4A84B"
GREEN  = "#1E8449"
RED    = "#C0392B"
AMBER  = "#D68910"
GREY   = "#717D7E"


def apply_professional_theme() -> None:
    """Inject professional CSS into the current page."""
    st.markdown("""
    <style>
    /* ── Base & background ──────────────────────────────────────────── */
    .stApp {
        background-color: #0f1117 !important;
    }
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1200px;
    }

    /* ── Typography ─────────────────────────────────────────────────── */
    h1 {
        font-weight: 800 !important;
        letter-spacing: -0.8px !important;
        font-size: 2rem !important;
        color: #f0f2f6 !important;
    }
    h2 {
        font-weight: 600 !important;
        letter-spacing: -0.3px !important;
        font-size: 1.1rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1.2px !important;
        color: rgba(240,242,246,0.75) !important;
        border-bottom: 1px solid rgba(212,168,75,0.2);
        padding-bottom: 8px;
        margin-top: 1.8rem !important;
        margin-bottom: 1rem !important;
    }
    h3 {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: rgba(240,242,246,0.9) !important;
    }

    /* ── Metric cards ───────────────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1a1d27 0%, #161820 100%);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 12px;
        padding: 1rem 1.2rem !important;
        transition: border-color 0.2s;
    }
    [data-testid="metric-container"]:hover {
        border-color: rgba(212,168,75,0.35);
    }
    [data-testid="stMetricValue"] {
        font-size: 1.85rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.8px;
        color: #f0f2f6 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.68rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1.8px !important;
        font-weight: 700 !important;
        color: rgba(212,168,75,0.85) !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.78rem !important;
        font-weight: 500 !important;
    }

    /* ── Sidebar ────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background-color: #13151f !important;
        border-right: 1px solid rgba(212,168,75,0.2) !important;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        color: rgba(240,242,246,0.85);
    }

    /* ── Dividers ───────────────────────────────────────────────────── */
    hr {
        border-color: rgba(255,255,255,0.06) !important;
        margin: 1.2rem 0 !important;
    }

    /* ── Dataframe / tables ─────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 10px !important;
        overflow: hidden;
    }

    /* ── Alerts / banners ───────────────────────────────────────────── */
    [data-testid="stAlert"] {
        border-radius: 10px !important;
    }

    /* ── Buttons ────────────────────────────────────────────────────── */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        border-color: #D4A84B !important;
        color: #D4A84B !important;
    }

    /* ── Captions & helpers ─────────────────────────────────────────── */
    .report-eyebrow {
        font-size: 0.62rem;
        text-transform: uppercase;
        letter-spacing: 3px;
        color: #D4A84B;
        font-weight: 800;
        margin-bottom: 4px;
        opacity: 0.9;
    }
    .report-subtitle {
        font-size: 0.83rem;
        color: rgba(240,242,246,0.45);
        margin-bottom: 0.6rem;
        margin-top: -4px;
    }

    /* ── KPI accent cards ───────────────────────────────────────────── */
    .kpi-green  { border-left: 3px solid #27ae60 !important; }
    .kpi-amber  { border-left: 3px solid #f39c12 !important; }
    .kpi-red    { border-left: 3px solid #e74c3c !important; }
    .kpi-blue   { border-left: 3px solid #3498db !important; }
    .kpi-gold   { border-left: 3px solid #D4A84B !important; }

    /* ── Section header helper ──────────────────────────────────────── */
    .section-label {
        font-size: 0.62rem;
        text-transform: uppercase;
        letter-spacing: 2.5px;
        color: rgba(212,168,75,0.7);
        font-weight: 700;
        margin-bottom: 6px;
        margin-top: 1.6rem;
        display: block;
    }

    /* ── Health score badge ─────────────────────────────────────────── */
    .health-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .health-good    { background: rgba(39,174,96,0.15);  color: #27ae60; border: 1px solid rgba(39,174,96,0.3); }
    .health-warning { background: rgba(243,156,18,0.15); color: #f39c12; border: 1px solid rgba(243,156,18,0.3); }
    .health-alert   { background: rgba(231,76,60,0.15);  color: #e74c3c; border: 1px solid rgba(231,76,60,0.3); }

    /* ── Print CSS ──────────────────────────────────────────────────── */
    @media print {
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="collapsedControl"],
        .stButton,
        iframe { display: none !important; }
        .block-container {
            padding: 0 !important;
            max-width: 100% !important;
        }
        h1, h2, h3 { color: #1B4F72 !important; }
        [data-testid="stMetricValue"] { color: #1B4F72 !important; }
    }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", eyebrow: str = "Business Intelligence") -> None:
    """Render a professional page header."""
    st.markdown(f'<p class="report-eyebrow">{eyebrow}</p>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="report-subtitle">{subtitle}</p>', unsafe_allow_html=True)


def section_header(label: str) -> None:
    """Render a small uppercase section label above a group of content."""
    st.markdown(f'<span class="section-label">{label}</span>', unsafe_allow_html=True)


def health_badge(label: str, status: str) -> str:
    """Return HTML for a colored health badge. status: 'good' | 'warning' | 'alert'."""
    return f'<span class="health-badge health-{status}">{label}</span>'
