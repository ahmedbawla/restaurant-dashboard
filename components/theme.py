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
    /* ── Typography ─────────────────────────────────────────────────── */
    h1 {
        font-weight: 700 !important;
        letter-spacing: -0.5px !important;
    }
    h2 {
        font-weight: 600 !important;
        letter-spacing: -0.3px !important;
        border-bottom: 2px solid rgba(212,168,75,0.35);
        padding-bottom: 6px;
        margin-top: 1.4rem !important;
    }
    h3 { font-weight: 600 !important; }

    /* ── Layout ─────────────────────────────────────────────────────── */
    .block-container { padding-top: 1rem !important; }

    /* ── Metric cards ───────────────────────────────────────────────── */
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.7rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
        font-weight: 700 !important;
        opacity: 0.65;
    }
    [data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

    /* ── Sidebar ────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(212,168,75,0.25) !important;
    }

    /* ── Captions & helpers ─────────────────────────────────────────── */
    .report-eyebrow {
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 2.5px;
        color: #D4A84B;
        font-weight: 700;
        margin-bottom: 2px;
    }
    .report-subtitle {
        font-size: 0.82rem;
        opacity: 0.6;
        margin-bottom: 0.5rem;
    }

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
