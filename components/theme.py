"""
TableMetrics dark theme — red/orange glow aesthetic.
Call apply_professional_theme() at the top of each page (via app.py).
"""

import streamlit as st

# Brand palette
ACCENT   = "#FF6B35"   # primary orange
ACCENT2  = "#FF4B4B"   # red
ACCENT3  = "#FF8C42"   # light orange
GREEN    = "#2ecc71"
AMBER    = "#f39c12"
RED      = "#e74c3c"
GREY     = "#6b7280"


def apply_professional_theme() -> None:
    """Inject the TableMetrics dark theme CSS into the current page."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    /* ── Base & background ──────────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #0a0a0c !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stMain"] {
        background: transparent !important;
    }
    .block-container {
        padding-top: 1.4rem !important;
        padding-bottom: 2rem !important;
        max-width: 1280px;
    }

    /* ── Typography ─────────────────────────────────────────────────── */
    h1 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 800 !important;
        letter-spacing: -0.8px !important;
        font-size: 1.9rem !important;
        color: #f0f2f6 !important;
    }
    h2 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
        color: rgba(240,242,246,0.6) !important;
        border-bottom: 1px solid rgba(255,107,53,0.15);
        padding-bottom: 8px;
        margin-top: 1.8rem !important;
        margin-bottom: 1rem !important;
    }
    h3 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: rgba(240,242,246,0.9) !important;
    }
    p, li, span, div {
        font-family: 'Inter', sans-serif !important;
    }

    /* ── Metric cards ───────────────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 14px !important;
        padding: 1.1rem 1.3rem !important;
        transition: border-color 0.25s, box-shadow 0.25s;
        backdrop-filter: blur(8px);
    }
    [data-testid="metric-container"]:hover {
        border-color: rgba(255,107,53,0.45) !important;
        box-shadow: 0 0 24px rgba(255,107,53,0.12);
    }
    [data-testid="stMetricValue"] {
        font-size: 1.9rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.8px !important;
        color: #f0f2f6 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.65rem !important;
        text-transform: uppercase !important;
        letter-spacing: 2px !important;
        font-weight: 700 !important;
        color: rgba(255,107,53,0.85) !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.78rem !important;
        font-weight: 500 !important;
    }

    /* ── Sidebar ────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background-color: #0d0d0f !important;
        border-right: 1px solid rgba(255,107,53,0.18) !important;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        color: rgba(240,242,246,0.75);
        font-size: 0.88rem;
    }
    /* Sidebar nav items */
    [data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a {
        border-radius: 8px !important;
        transition: background 0.2s, color 0.2s !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a:hover {
        background: rgba(255,107,53,0.12) !important;
    }
    [data-testid="stSidebar"] [aria-current="page"] {
        background: rgba(255,107,53,0.15) !important;
        border-left: 3px solid #FF6B35 !important;
    }

    /* ── Dividers ───────────────────────────────────────────────────── */
    hr {
        border: none !important;
        height: 1px !important;
        background: rgba(255,255,255,0.06) !important;
        margin: 1.2rem 0 !important;
    }

    /* ── Buttons ────────────────────────────────────────────────────── */
    .stButton > button {
        font-family: 'Inter', sans-serif !important;
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        transition: all 0.2s !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        background: rgba(255,255,255,0.05) !important;
        color: rgba(240,242,246,0.85) !important;
    }
    .stButton > button:hover {
        border-color: rgba(255,107,53,0.6) !important;
        color: #FF6B35 !important;
        background: rgba(255,107,53,0.08) !important;
        box-shadow: 0 0 16px rgba(255,107,53,0.15) !important;
    }
    /* Primary buttons */
    .stButton > button[kind="primary"],
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #FF6B35 0%, #FF4B4B 100%) !important;
        border: none !important;
        color: #fff !important;
        box-shadow: 0 4px 15px rgba(255,75,75,0.3) !important;
    }
    .stButton > button[kind="primary"]:hover,
    [data-testid="baseButton-primary"]:hover {
        opacity: 0.88 !important;
        box-shadow: 0 4px 22px rgba(255,75,75,0.45) !important;
    }

    /* ── Selectbox / inputs ──────────────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] > div > div > input,
    [data-testid="stDateInput"] > div > div > input {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 8px !important;
        color: #f0f2f6 !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stSelectbox"] > div > div:focus-within,
    [data-testid="stTextInput"] > div > div:focus-within {
        border-color: rgba(255,107,53,0.5) !important;
        box-shadow: 0 0 0 2px rgba(255,107,53,0.15) !important;
    }

    /* ── Forms ───────────────────────────────────────────────────────── */
    [data-testid="stForm"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 12px !important;
        padding: 0.5rem !important;
    }

    /* ── Dataframe / tables ─────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 12px !important;
        overflow: hidden;
    }
    [data-testid="stDataFrame"] thead tr th {
        background: rgba(255,107,53,0.08) !important;
        color: rgba(255,107,53,0.9) !important;
        font-size: 0.68rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
    }

    /* ── Alerts / banners ───────────────────────────────────────────── */
    [data-testid="stAlert"] {
        border-radius: 10px !important;
        border-left-width: 3px !important;
    }

    /* ── Expander ────────────────────────────────────────────────────── */
    [data-testid="stExpander"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 12px !important;
    }
    [data-testid="stExpander"]:hover {
        border-color: rgba(255,107,53,0.25) !important;
    }

    /* ── Tab bar ─────────────────────────────────────────────────────── */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.03) !important;
        border-radius: 10px !important;
        padding: 3px !important;
        gap: 4px !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        border-radius: 7px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        color: rgba(240,242,246,0.55) !important;
        transition: all 0.2s !important;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background: rgba(255,107,53,0.18) !important;
        color: #FF6B35 !important;
    }

    /* ── Caption & helper text ───────────────────────────────────────── */
    .stCaption, [data-testid="stCaptionContainer"] p {
        color: rgba(240,242,246,0.35) !important;
        font-size: 0.75rem !important;
    }

    /* ── Captions & helpers ─────────────────────────────────────────── */
    .report-eyebrow {
        font-size: 0.62rem;
        text-transform: uppercase;
        letter-spacing: 3px;
        color: rgba(255,107,53,0.8);
        font-weight: 800;
        margin-bottom: 4px;
        opacity: 0.9;
    }
    .report-subtitle {
        font-size: 0.83rem;
        color: rgba(240,242,246,0.4);
        margin-bottom: 0.6rem;
        margin-top: -4px;
    }

    /* ── KPI accent cards ───────────────────────────────────────────── */
    .kpi-green  { border-left: 3px solid #2ecc71 !important; }
    .kpi-amber  { border-left: 3px solid #f39c12 !important; }
    .kpi-red    { border-left: 3px solid #e74c3c !important; }
    .kpi-blue   { border-left: 3px solid #3498db !important; }
    .kpi-orange { border-left: 3px solid #FF6B35 !important; }

    /* ── Section header helper ──────────────────────────────────────── */
    .section-label {
        font-size: 0.62rem;
        text-transform: uppercase;
        letter-spacing: 2.5px;
        color: rgba(255,107,53,0.75);
        font-weight: 700;
        margin-bottom: 6px;
        margin-top: 1.6rem;
        display: block;
    }

    /* ── Health score badge ─────────────────────────────────────────── */
    .health-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .health-good    { background: rgba(46,204,113,0.12);  color: #2ecc71; border: 1px solid rgba(46,204,113,0.3); }
    .health-warning { background: rgba(243,156,18,0.12);  color: #f39c12; border: 1px solid rgba(243,156,18,0.3); }
    .health-alert   { background: rgba(255,75,75,0.12);   color: #FF4B4B; border: 1px solid rgba(255,75,75,0.3); }

    /* ── Spinner / progress ─────────────────────────────────────────── */
    [data-testid="stSpinner"] > div {
        border-top-color: #FF6B35 !important;
    }

    /* ── Print CSS ──────────────────────────────────────────────────── */
    @media print {
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="collapsedControl"],
        .stButton, iframe { display: none !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
        h1, h2, h3 { color: #111 !important; }
        [data-testid="stMetricValue"] { color: #111 !important; }
    }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", eyebrow: str = "Business Intelligence") -> None:
    """Render a branded page header."""
    st.markdown(f'<p class="report-eyebrow">{eyebrow}</p>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="report-subtitle">{subtitle}</p>', unsafe_allow_html=True)


def section_header(label: str, help: str = None) -> None:
    """Render a small uppercase section label with optional tooltip."""
    icon = (
        f'&nbsp;<span title="{help}" style="cursor:help;color:rgba(255,107,53,0.45);'
        f'font-size:0.95rem;vertical-align:middle;font-weight:400;letter-spacing:0;'
        f'text-transform:none;">ⓘ</span>'
        if help else ""
    )
    st.markdown(f'<span class="section-label">{label}{icon}</span>', unsafe_allow_html=True)


def health_badge(label: str, status: str) -> str:
    """Return HTML for a colored health badge. status: 'good' | 'warning' | 'alert'."""
    return f'<span class="health-badge health-{status}">{label}</span>'
