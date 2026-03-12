"""
Generate the TableMetrics Application Overview & User Guide PDF.
Run from the project root:  python generate_app_guide.py
"""

import io
import sys
from datetime import date as dt_date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether,
    NextPageTemplate, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

# ── Brand palette ─────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#1B4F72")
NAVY_DARK = colors.HexColor("#0D2E43")
GOLD      = colors.HexColor("#D4A84B")
GOLD_LIGHT= colors.HexColor("#F0E0B0")
GREEN     = colors.HexColor("#1E8449")
RED       = colors.HexColor("#C0392B")
AMBER     = colors.HexColor("#D68910")
ROW_ALT   = colors.HexColor("#F4F6F9")
LIGHT_RULE= colors.HexColor("#DDE1E7")
TEXT_DARK = colors.HexColor("#1A1A2A")
TEXT_GREY = colors.HexColor("#5D6D7E")
TIP_BG    = colors.HexColor("#EAF4FB")
TIP_LINE  = colors.HexColor("#3498DB")
NOTE_BG   = colors.HexColor("#FDFBF3")

PAGE_W, PAGE_H = A4
MARGIN    = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
TODAY     = dt_date.today().strftime("%B %d, %Y")


# ── Styles ────────────────────────────────────────────────────────────────────
def _S():
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold",
                             fontSize=18, textColor=NAVY, leading=22,
                             spaceBefore=6, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold",
                             fontSize=12, textColor=NAVY, leading=16,
                             spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold",
                             fontSize=10, textColor=TEXT_DARK, leading=14,
                             spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("body", fontName="Helvetica",
                               fontSize=9, textColor=TEXT_DARK, leading=14,
                               spaceBefore=2, spaceAfter=2),
        "body_j": ParagraphStyle("body_j", fontName="Helvetica",
                                  fontSize=9, textColor=TEXT_DARK, leading=14,
                                  alignment=TA_JUSTIFY, spaceBefore=2, spaceAfter=2),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica",
                                  fontSize=9, textColor=TEXT_DARK, leading=13,
                                  leftIndent=12, spaceBefore=1, spaceAfter=1),
        "small": ParagraphStyle("small", fontName="Helvetica",
                                 fontSize=8, textColor=TEXT_GREY, leading=11),
        "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique",
                                   fontSize=8, textColor=TEXT_GREY, leading=11,
                                   spaceBefore=2),
        "tbl_hdr": ParagraphStyle("tbl_hdr", fontName="Helvetica-Bold",
                                   fontSize=8, textColor=colors.white, leading=11),
        "tbl_cell": ParagraphStyle("tbl_cell", fontName="Helvetica",
                                    fontSize=8, textColor=TEXT_DARK, leading=11),
        "tbl_cell_b": ParagraphStyle("tbl_cell_b", fontName="Helvetica-Bold",
                                      fontSize=8, textColor=TEXT_DARK, leading=11),
        "toc": ParagraphStyle("toc", fontName="Helvetica",
                               fontSize=10, textColor=TEXT_DARK, leading=18,
                               leftIndent=0),
        "toc_sub": ParagraphStyle("toc_sub", fontName="Helvetica",
                                   fontSize=9, textColor=TEXT_GREY, leading=14,
                                   leftIndent=16),
        "cover_title": ParagraphStyle("cover_title", fontName="Helvetica-Bold",
                                       fontSize=42, textColor=colors.white,
                                       leading=48, alignment=TA_CENTER),
        "cover_sub": ParagraphStyle("cover_sub", fontName="Helvetica",
                                     fontSize=16, textColor=GOLD,
                                     leading=20, alignment=TA_CENTER),
        "cover_meta": ParagraphStyle("cover_meta", fontName="Helvetica",
                                      fontSize=10, textColor=colors.HexColor("#BDC3C7"),
                                      leading=14, alignment=TA_CENTER),
        "sec_label": ParagraphStyle("sec_label", fontName="Helvetica-Bold",
                                     fontSize=8, textColor=colors.white,
                                     letterSpacing=2, leading=10),
    }


# ── Layout helpers ────────────────────────────────────────────────────────────
def _rule():
    return HRFlowable(width="100%", thickness=0.5,
                      color=LIGHT_RULE, spaceAfter=4, spaceBefore=4)

def _gold_rule():
    return HRFlowable(width="100%", thickness=1.5,
                      color=GOLD, spaceAfter=6, spaceBefore=2)

def _sp(h=4):
    return Spacer(1, h * mm)


def _section_banner(title: str, S: dict) -> Table:
    """Navy full-width banner with gold underline."""
    tbl = Table([[Paragraph(title.upper(), S["sec_label"])]],
                colWidths=[CONTENT_W], rowHeights=[13 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("LINEBELOW",     (0,0), (-1,-1), 2, GOLD),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    return tbl


def _tip(text: str, S: dict, label: str = "TIP") -> Table:
    tbl = Table([[Paragraph(f"<b>{label}:</b>  {text}", S["body"])]],
                colWidths=[CONTENT_W - 2*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), TIP_BG),
        ("LINEBEFORE",    (0,0), (0,-1), 3, TIP_LINE),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ]))
    return tbl


def _note(text: str, S: dict) -> Table:
    return _tip(text, S, label="NOTE")


def _col_table(rows: list[tuple[str, str]], S: dict,
               headers: tuple = ("Column", "Description"),
               widths: tuple = (50*mm, None)) -> Table:
    """Two-column reference table."""
    w2 = widths[1] or (CONTENT_W - widths[0])
    data = [[Paragraph(h, S["tbl_hdr"]) for h in headers]]
    for col, desc in rows:
        data.append([Paragraph(col, S["tbl_cell_b"]),
                     Paragraph(desc, S["tbl_cell"])])
    tbl = Table(data, colWidths=[widths[0], w2], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.3, LIGHT_RULE),
        ("LINEBELOW",     (0,0), (-1,0), 1, GOLD),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return tbl


def _three_col_table(rows: list[tuple], S: dict,
                     headers: tuple = ("Column", "Type", "Description")) -> Table:
    w = [42*mm, 28*mm, CONTENT_W - 70*mm]
    data = [[Paragraph(h, S["tbl_hdr"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), S["tbl_cell_b"] if i == 0 else S["tbl_cell"])
                     for i, c in enumerate(r)])
    tbl = Table(data, colWidths=w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.3, LIGHT_RULE),
        ("LINEBELOW",     (0,0), (-1,0), 1, GOLD),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return tbl


def B(text, S):
    return Paragraph(text, S["bullet"])


def P(text, S, style="body"):
    return Paragraph(text, S[style])


# ── Page templates ────────────────────────────────────────────────────────────
def _make_doc(buf):
    def _cover_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(NAVY_DARK)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h * 0.38, w, 2, fill=1, stroke=0)
        canvas.restoreState()

    def _body_page(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Header band
        canvas.setFillColor(NAVY_DARK)
        canvas.rect(0, h - 18*mm, w, 18*mm, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 18*mm, w, 1*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN, h - 10*mm, "TableMetrics")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#BDC3C7"))
        canvas.drawRightString(w - MARGIN, h - 10*mm, "Application Overview & User Guide")
        # Footer
        canvas.setFillColor(LIGHT_RULE)
        canvas.rect(MARGIN, 10*mm, w - 2*MARGIN, 0.3*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT_GREY)
        canvas.drawString(MARGIN, 6.5*mm, f"Confidential  ·  TableMetrics")
        canvas.drawRightString(w - MARGIN, 6.5*mm,
                               f"Page {doc.page}  ·  Generated {TODAY}")
        canvas.restoreState()

    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, leftPadding=MARGIN,
                        rightPadding=MARGIN, topPadding=PAGE_H*0.42,
                        bottomPadding=20*mm)
    body_frame  = Frame(MARGIN, 16*mm, CONTENT_W, PAGE_H - 36*mm,
                        leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=22*mm, bottomMargin=18*mm,
        title="TableMetrics — Application Overview & User Guide",
        author="TableMetrics",
    )
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=_cover_page),
        PageTemplate(id="Body",  frames=[body_frame],  onPage=_body_page),
    ])
    return doc


# ── Content builders ──────────────────────────────────────────────────────────
def _cover(S):
    story = []
    story.append(NextPageTemplate("Body"))
    story.append(Paragraph("TableMetrics", S["cover_title"]))
    story.append(_sp(6))
    story.append(Paragraph("Application Overview &amp; User Guide", S["cover_sub"]))
    story.append(_sp(4))
    story.append(Paragraph(
        "Restaurant Intelligence Platform  ·  Confidential", S["cover_meta"]))
    story.append(_sp(2))
    story.append(Paragraph(f"Generated {TODAY}", S["cover_meta"]))
    story.append(PageBreak())
    return story


def _toc(S):
    story = []
    story.append(_section_banner("Table of Contents", S))
    story.append(_sp(4))

    sections = [
        ("1", "Application Overview",            "What TableMetrics does and who it is for"),
        ("2", "Authentication & Accounts",        "Creating accounts, logging in, demo mode"),
        ("3", "Global Controls",                  "Date range selector, Sync Now, data modes"),
        ("4", "Summary Dashboard",                "Business health score, KPIs, revenue overview"),
        ("5", "Spending & Expenses",              "QuickBooks Online integration and expense data"),
        ("6", "Payroll & Labour",                 "Paychex CSV import and workforce analytics"),
        ("7", "Menu Mix & Item Performance",      "Toast POS item-level data and menu analytics"),
        ("8", "Sales Analysis",                   "Toast POS daily and hourly sales data"),
        ("9", "Reports & Analytics",              "Generating, previewing, and exporting reports"),
        ("10","Account Settings",                 "Profile management and password changes"),
        ("11","Database Tables Reference",        "Column-by-column reference for all data tables"),
        ("12","Data Flow Summary",                "How data moves from source systems to the dashboard"),
    ]

    for num, title, desc in sections:
        story.append(Paragraph(f"<b>{num}.  {title}</b>", S["toc"]))
        story.append(Paragraph(desc, S["toc_sub"]))

    story.append(PageBreak())
    return story


def _section1_overview(S):
    story = []
    story.append(_section_banner("1. Application Overview", S))
    story.append(_sp(3))
    story.append(P("TableMetrics is a web-based restaurant intelligence platform built on Streamlit. "
                   "It aggregates financial, payroll, and sales data from three source systems — "
                   "QuickBooks Online, Paychex Flex, and Toast POS — into a single, secure dashboard "
                   "that gives restaurant owners and operators a clear, real-time view of how their "
                   "business is performing.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>Core Capabilities</b>", S, "h2"))
    caps = [
        ("Revenue Tracking", "Daily revenue, guest covers, average check size, and spend-per-head trends sourced from Toast POS exports."),
        ("Payroll Analytics", "Weekly payroll totals, hours worked, headcount, and blended hourly rates from Paychex Flex CSV exports."),
        ("Expense Management", "Operating expense categorisation, vendor analysis, and weekly trend tracking via QuickBooks Online OAuth sync."),
        ("Menu Performance", "Item-level revenue, quantity sold, category breakdown, and revenue concentration (Pareto) analysis from Toast item reports."),
        ("Cash Flow", "Monthly inflow, outflow, and net position tracking imported from QuickBooks."),
        ("Automated Reporting", "PDF reports with data-driven insights and recommendations, generated on demand for any selected date range."),
        ("Business Health Score", "A composite signal on the Summary page that flags labour cost thresholds and other operational issues at a glance."),
    ]
    data = [[Paragraph(t, S["tbl_hdr"]) for t in ["Feature", "Description"]]]
    for feat, desc in caps:
        data.append([Paragraph(feat, S["tbl_cell_b"]), Paragraph(desc, S["tbl_cell"])])
    tbl = Table(data, colWidths=[52*mm, CONTENT_W - 52*mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.3, LIGHT_RULE),
        ("LINEBELOW",     (0,0), (-1,0), 1, GOLD),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    story.append(tbl)
    story.append(_sp(4))

    story.append(P("<b>Technology Stack</b>", S, "h2"))
    stack = [
        ("Frontend", "Streamlit (Python) — runs entirely in the browser, no separate frontend build required."),
        ("Backend / Database", "PostgreSQL hosted on Supabase. All data is partitioned by username for multi-tenant isolation."),
        ("Charts", "Plotly (via plotly.express and plotly.graph_objects) for all interactive visualisations."),
        ("PDF Generation", "ReportLab — all PDF reports are generated server-side and returned as bytes."),
        ("Authentication", "Username + bcrypt-hashed password stored in the users table. Session state managed by Streamlit."),
        ("OAuth", "QuickBooks Online uses OAuth 2.0. The app exchanges an authorization code for refresh/access tokens stored in the users table."),
    ]
    story.append(_col_table(stack, S, headers=("Component", "Details"),
                            widths=(48*mm, None)))
    story.append(PageBreak())
    return story


def _section2_auth(S):
    story = []
    story.append(_section_banner("2. Authentication & Accounts", S))
    story.append(_sp(3))
    story.append(P("TableMetrics uses a simple username + password authentication system. "
                   "All passwords are hashed with bcrypt before storage — plain-text passwords are "
                   "never stored.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>Creating an Account</b>", S, "h2"))
    for step in [
        "Navigate to the app URL. The landing page shows the TableMetrics branding with <b>Log In</b> and <b>Create Account</b> buttons.",
        "Click <b>Create Account</b> and fill in: Restaurant Name, Username, Email Address (optional), Phone Number (optional), Password, and Confirm Password.",
        "Password must be at least 6 characters. On submission the account is created and you are immediately logged in.",
        "Your restaurant name appears on all report headers and the sidebar.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(3))

    story.append(P("<b>Logging In</b>", S, "h2"))
    for step in [
        "Click <b>Log In</b> on the landing page.",
        "Enter your username and password.",
        "On success you are taken directly to the Summary dashboard.",
        "Your session persists until you click <b>Logout</b> in the sidebar.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(3))

    story.append(P("<b>Demo / Test Account</b>", S, "h2"))
    story.append(P("A <b>test</b> account is automatically created on every app startup if it does not "
                   "already exist (username: <b>test</b>, password: <b>test</b>). This account has access to "
                   "a <b>Load Demo Data</b> button in the sidebar that populates simulated restaurant data, "
                   "allowing anyone to explore the full dashboard without connecting real integrations.", S, "body_j"))
    story.append(_sp(2))
    story.append(_note("The demo account's restaurant name is 'The Daily Grind (Demo)'. "
                       "Demo data is clearly labelled in the page subtitle.", S))
    story.append(PageBreak())
    return story


def _section3_controls(S):
    story = []
    story.append(_section_banner("3. Global Controls", S))
    story.append(_sp(3))
    story.append(P("Every page in TableMetrics shares the same sidebar. The sidebar contains global "
                   "controls that affect the date range and data shown across all pages.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>Date Range Selector</b>", S, "h2"))
    story.append(P("A dropdown labelled <b>View</b> controls the analysis period. The available options are:", S))
    views = [
        ("Weekly",          "The last 7 days of available data (end of dataset − 6 days to end)."),
        ("Monthly",         "Rolling 30 days ending today."),
        ("Current Quarter", "From the first day to the last day of the calendar quarter that contains today."),
        ("Last Quarter",    "The full previous calendar quarter (Q1=Jan–Mar, Q2=Apr–Jun, etc.)."),
        ("Annual",          "Rolling 365 days ending today."),
        ("Custom",          "Two date pickers appear. You select the start and end date manually within the range of available data."),
    ]
    story.append(_col_table(views, S, headers=("View Option", "Date Range Logic"),
                            widths=(38*mm, None)))
    story.append(_sp(3))
    story.append(_tip("All view modes clamp to the actual date range of data in the database. "
                      "If no data exists for the selected period, the view falls back to the most recent available date.", S))
    story.append(_sp(4))

    story.append(P("<b>Sync Now Button</b>", S, "h2"))
    story.append(P("The <b>Sync Now</b> button in the sidebar triggers a live data pull from all connected "
                   "integrations (QuickBooks, Paychex, Toast if scraper credentials are stored). "
                   "Results appear as flash messages below the button: success (rows synced), "
                   "warning (0 rows returned), or info (integration not yet connected).", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>Data Modes</b>", S, "h2"))
    modes = [
        ("Live Data",      "Default for all real accounts. Data comes from the connected integrations and CSV uploads."),
        ("Simulated Data", "Only available on the test account via 'Load Demo Data'. Fills all tables with synthetic restaurant data for demonstration purposes."),
    ]
    story.append(_col_table(modes, S, headers=("Mode", "Description"), widths=(38*mm, None)))
    story.append(PageBreak())
    return story


def _section4_summary(S):
    story = []
    story.append(_section_banner("4. Summary Dashboard", S))
    story.append(_sp(3))
    story.append(P("The Summary page is the main landing page after login. It is designed as a "
                   "<b>shareholder-level overview</b> — it shows the most important numbers across all "
                   "data sources simultaneously. It gracefully handles partial data: if only sales data "
                   "is connected but not payroll, it still renders with whatever is available.", S, "body_j"))
    story.append(_sp(3))

    sections = [
        ("Business Health Score",
         "A badge at the top of the page that evaluates key thresholds and shows one of three statuses: "
         "All Systems Healthy (green), Watch Closely (amber), or Needs Attention (red). "
         "Currently evaluates labour cost % against the configured target and warning thresholds. "
         "When issues are present, an expandable panel shows the specific alert with context."),
        ("Most Recent Day",
         "KPI strip showing the latest date in the dataset: Daily Revenue, Guest Covers, Avg. Check. "
         "If labour data is also available for that date, Labour % and Rev per Labour Hour are shown as well."),
        ("Period Summary",
         "Five KPIs for the entire selected date range: Total Revenue (with half-over-half delta), "
         "Total Covers (with delta), Avg. Check Size (with delta), Total Labour Cost (as % of revenue), "
         "and Total QB Expenses (as % of revenue). Deltas compare the second half of the period to the first."),
        ("Revenue Trend",
         "A daily revenue area chart with a 7-day rolling average overlay for the full selected period."),
        ("Traffic & Spend Analysis",
         "Two charts side-by-side: (1) Total revenue by day of week — identifies your strongest and "
         "weakest trading days. (2) Revenue per cover (spend-per-head) trend over time."),
        ("Performance Extremes",
         "Four metrics: best revenue day and its amount, average daily revenue, lowest revenue day, "
         "and the date with the highest average check size."),
        ("Labour Efficiency",
         "Total labour cost, labour % of revenue (colour-coded vs target), total hours worked, "
         "and revenue per labour hour. Also shows a daily labour % trend line with target/warning "
         "reference lines, and a full payroll summary table aggregated across all weeks in the period."),
        ("Revenue Breakdown",
         "Only shown when Sales + Labour + Expenses are all connected. Shows how each dollar "
         "of revenue is allocated: labour cost, operating expenses, and the remainder. "
         "Includes a horizontal bar chart for visual comparison. Note: food/COGS is not included."),
        ("Spending Overview",
         "Quick summary of QuickBooks expenses: total spend, largest category, pending review "
         "amount, and unique vendor count. Shows top 5 categories by spend."),
        ("Menu Mix Snapshot",
         "Category revenue bar chart and a top-5 items table. Only shown when menu item data is available."),
    ]

    for title, desc in sections:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(PageBreak())
    return story


def _section5_spending(S):
    story = []
    story.append(_section_banner("5. Spending & Expenses", S))
    story.append(_sp(3))
    story.append(P("<b>Data Source: QuickBooks Online (OAuth 2.0)</b>", S, "h2"))
    story.append(P("The Spending page pulls operating expense data from QuickBooks Online via "
                   "an OAuth 2.0 integration. Once connected, the app stores a refresh token in the "
                   "database and exchanges it for access tokens automatically on each sync.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>How to Connect QuickBooks</b>", S, "h3"))
    for step in [
        "Navigate to the <b>Spending</b> page. If not connected, a red badge reads 'Not Connected'.",
        "Click <b>Connect QuickBooks</b>. A green button labelled <b>Open QuickBooks ↗</b> will appear.",
        "Click <b>Open QuickBooks ↗</b> — this opens the Intuit authorization page in a new tab.",
        "Log in with your QuickBooks credentials and grant the requested permissions.",
        "Intuit redirects back to the app with an authorization code. The app exchanges this for tokens, stores them, and immediately syncs your data.",
        "On success you are redirected to Account Settings and a confirmation message shows how many rows were imported.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(2))
    story.append(_tip("QuickBooks credentials (client_id, client_secret, redirect_uri) must be "
                      "configured in .streamlit/secrets.toml under the [quickbooks] section before "
                      "the Connect button appears.", S))
    story.append(_sp(4))

    story.append(P("<b>What Data is Pulled</b>", S, "h3"))
    story.append(P("The connector queries three QuickBooks transaction types for the configured date range:", S))
    qb_sources = [
        ("Purchase", "Credit card transactions, checks, and cash payments. This is the primary source of day-to-day operating expenses."),
        ("Bill", "Accounts payable invoices entered into QuickBooks from vendors. Captures expenses that are invoiced before payment."),
        ("JournalEntry", "Manual journal entries — used for payroll journal entries, depreciation, accruals, and other accounting adjustments."),
    ]
    story.append(_col_table(qb_sources, S, headers=("Transaction Type", "What it captures"),
                            widths=(40*mm, None)))
    story.append(_sp(3))
    story.append(_note("Transactions labelled 'Pending Review' in QuickBooks (uncategorised bank feed "
                       "items) are imported as category = 'Pending Review'. They are included in all "
                       "totals but flagged separately. Categorise them in QBO → Banking → For Review.", S))
    story.append(_sp(4))

    story.append(P("<b>Page Sections Explained</b>", S, "h2"))
    page_sections = [
        ("Expense Overview KPIs",
         "Total Spend, Avg. Daily Spend, Largest Category (with its % of total), Top Vendor, "
         "and Unique Vendor count. The Total Spend delta compares the second half of the period to the first."),
        ("Breakdown Charts",
         "Left: donut chart showing each expense category as a share of total spend. "
         "Right: horizontal bar chart of top vendors by total amount paid in the period."),
        ("Weekly Trend",
         "Bar chart of total spend per calendar week with a 4-week rolling average dotted overlay. "
         "Shows whether spending is accelerating or decelerating."),
        ("Category Summary Table",
         "One row per expense category with: Total Spend, # Transactions, and Avg Transaction size."),
        ("Transaction Detail Table",
         "Every individual expense line item from QuickBooks for the period, sorted by most recent first. "
         "Filterable by category using the sidebar multiselect."),
        ("QuickBooks Diagnostics",
         "Expandable panel (only shown when connected) that queries QBO directly and reports "
         "how many transactions and what total dollar value each source type returned for the last 90 days. "
         "Useful for diagnosing missing data."),
    ]
    for title, desc in page_sections:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(_sp(3))
    story.append(P("<b>Sidebar Filter</b>", S, "h3"))
    story.append(P("A Category multiselect in the sidebar filters all charts and tables on the "
                   "Spending page simultaneously. All categories are selected by default.", S))
    story.append(PageBreak())
    return story


def _section6_payroll(S):
    story = []
    story.append(_section_banner("6. Payroll & Labour", S))
    story.append(_sp(3))
    story.append(P("<b>Data Source: Paychex Flex (CSV Upload)</b>", S, "h2"))
    story.append(P("Payroll data is imported manually via CSV or Excel upload. There is no "
                   "automated scraper for Paychex — the user exports a report from Paychex Flex "
                   "and uploads it directly in the app.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>How to Export from Paychex Flex</b>", S, "h3"))
    for step in [
        "Log in to Paychex Flex.",
        "Navigate to <b>Reports → Payroll → Payroll Labor Cost</b>.",
        "Select the desired date range (export as wide a range as available — data is merged, nothing is overwritten).",
        "Click <b>Download</b> and select CSV format.",
        "In TableMetrics, navigate to the <b>Payroll</b> page and expand <b>Update Paychex Data</b>.",
        "Upload the file. The parser shows a preview of how many employee-week rows and pay periods were found.",
        "Click <b>Import to Dashboard</b> to save the data.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(2))
    story.append(_tip("You can upload multiple exports covering different date ranges. "
                      "New rows are merged into the existing data; existing rows are never duplicated "
                      "or overwritten.", S))
    story.append(_sp(4))

    story.append(P("<b>Page Sections Explained</b>", S, "h2"))
    page_secs = [
        ("Period Overview KPIs",
         "Five metrics across the full selected date range: Total Payroll (sum of all gross pay), "
         "Total Hours, Headcount (unique employees), Avg Hourly Rate (gross pay ÷ hours), "
         "and Pay Periods (number of distinct weekly pay periods)."),
        ("Weekly Payroll Trend",
         "Bar chart of total gross pay per pay period across the selected range, with a "
         "4-week rolling average overlay. Shows whether payroll is trending up or down."),
        ("Week of [Date] — Breakdown",
         "Filtered to the single week selected in the sidebar. Shows: Weekly Payroll, Hours Worked, "
         "and Employees for that week. Also contains two side-by-side horizontal bar charts: "
         "Top Earners (gross pay by employee, top 15) and Hours Worked by Employee (top 15)."),
        ("Pay & Hours by Role",
         "For the selected week: a grouped chart showing total gross pay (bars, left axis) "
         "and total hours (line, right axis) per job role."),
        ("Payroll Detail Table",
         "Full employee-level detail for the selected week: Employee, Department, Role, "
         "Employment Type, Regular Hrs, Total Hrs, and Gross Pay."),
    ]
    for title, desc in page_secs:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(_sp(2))
    story.append(P("<b>Sidebar Filter</b>", S, "h3"))
    story.append(P("A <b>Payroll Week</b> dropdown lists all pay period start dates within the "
                   "selected date range, sorted newest first. Selecting a week updates the "
                   "weekly breakdown sections while leaving the period-level KPIs and trend chart unchanged.", S))
    story.append(PageBreak())
    return story


def _section7_inventory(S):
    story = []
    story.append(_section_banner("7. Menu Mix & Item Performance", S))
    story.append(_sp(3))
    story.append(P("<b>Data Source: Toast POS (CSV Upload)</b>", S, "h2"))
    story.append(P("Menu item data is imported from Toast POS via the Item Selections report. "
                   "This data does not have a date dimension — it represents cumulative item "
                   "performance for the period covered by the export.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>How to Export from Toast</b>", S, "h3"))
    for step in [
        "Log in to Toast POS backend.",
        "Navigate to <b>Reports → Menu → Item Selections</b>.",
        "Click <b>Export</b> and select <b>All levels.csv</b>.",
        "In TableMetrics, go to the <b>Inventory</b> (Menu Mix) page.",
        "Upload the CSV. A preview shows how many items and categories were found.",
        "Click <b>Import to Dashboard</b>.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(4))

    story.append(P("<b>Page Sections Explained</b>", S, "h2"))
    inv_secs = [
        ("Menu Overview KPIs",
         "Total Menu Items (count of distinct items), Total Qty Sold, Total Menu Revenue, "
         "Avg Menu Price, and Top Category by revenue."),
        ("Sales by Category",
         "Two charts: a horizontal bar showing each category's revenue with its percentage share "
         "labelled, and a donut chart showing revenue share by category."),
        ("Top Performers",
         "Two horizontal bar charts side-by-side: Top 10 items by total revenue (gold) and "
         "Top 10 items by quantity sold (green)."),
        ("Category Summary Table",
         "One row per category: # Items, Qty Sold, Total Revenue, Avg Price, and Revenue Share %."),
        ("Revenue Concentration (Pareto)",
         "A combined bar + line chart showing individual item revenue (bars) and cumulative "
         "revenue percentage (line) ranked from highest to lowest. A dashed orange reference line "
         "marks the 80% threshold — items to the left of that line generate 80% of menu revenue. "
         "This is the Pareto principle applied to menu analysis."),
        ("Item Detail Table",
         "Full item list with: Item Name, Category, Price, Qty Sold, Total Revenue, Revenue Share %, "
         "and Revenue Rank. Filterable by category via the sidebar."),
    ]
    for title, desc in inv_secs:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(PageBreak())
    return story


def _section8_sales(S):
    story = []
    story.append(_section_banner("8. Sales Analysis", S))
    story.append(_sp(3))
    story.append(P("<b>Data Source: Toast POS (CSV Upload)</b>", S, "h2"))
    story.append(P("Daily and hourly sales data is imported from Toast POS via the Sales Summary "
                   "report. Multiple exports covering different date ranges can be uploaded and "
                   "they are automatically merged.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>How to Export from Toast</b>", S, "h3"))
    for step in [
        "Log in to Toast POS backend.",
        "Navigate to <b>Reports → Sales → Sales Summary</b>.",
        "Set the date range and click <b>Export</b>.",
        "In TableMetrics, go to the <b>Sales</b> page.",
        "Upload the CSV. A preview shows the date range covered.",
        "Click <b>Import to Dashboard</b>. Multiple files can be uploaded one at a time — data is merged.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(4))

    story.append(P("<b>Page Sections Explained</b>", S, "h2"))
    sales_secs = [
        ("Period KPIs",
         "Five metrics: Total Revenue (with half-over-half delta), Total Covers (with delta), "
         "Avg. Check Size (with delta), Best Day Revenue (with its date), and Rev per Cover "
         "(total revenue ÷ total covers). Deltas compare second half vs first half of the period."),
        ("Revenue Trend",
         "Daily revenue area chart with 7-day rolling average for the full selected period."),
        ("Peak Hours Heatmap",
         "A heatmap of average revenue by hour of day (columns) and day of week (rows). "
         "Darker/warmer colours indicate higher revenue. Useful for staffing decisions and "
         "identifying under-performing time slots. Requires hourly sales data."),
        ("Traffic Patterns",
         "Two charts: (1) Total revenue by day of week — identifies your best and worst days. "
         "(2) Average covers and average revenue by day of week on the same chart."),
        ("Spend Trends",
         "Two charts: (1) Average check size per day with 7-day rolling average — shows "
         "whether guests are spending more or less per visit over time. "
         "(2) Revenue per cover (spend-per-head) trend over time."),
        ("Top-Performing Menu Items",
         "Only shown when menu data is also loaded. Two horizontal bar charts: "
         "top 10 items by revenue and top 10 items by quantity sold."),
        ("Daily Sales Detail Table",
         "Day-by-day breakdown sorted most recent first: Date, Covers, Revenue, Avg. Check."),
    ]
    for title, desc in sales_secs:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(PageBreak())
    return story


def _section9_reports(S):
    story = []
    story.append(_section_banner("9. Reports & Analytics", S))
    story.append(_sp(3))
    story.append(P("The Reports page generates multi-section performance reports based on the "
                   "selected date range and available data. Reports can be previewed on-screen "
                   "or downloaded as a PDF.", S, "body_j"))
    story.append(_sp(3))

    story.append(P("<b>How to Generate a Report</b>", S, "h3"))
    for step in [
        "Select the desired date range using the global sidebar selector.",
        "Check or uncheck the section boxes to include or exclude: Executive Summary, Revenue & Sales, Labour & Payroll, Food Cost & Inventory, Expense Analysis, Cash Flow.",
        "Click <b>Preview Report</b> to render the report on-screen, or <b>Download PDF</b> to generate and download the PDF immediately.",
    ]:
        story.append(B(f"• {step}", S))
    story.append(_sp(4))

    story.append(P("<b>Report Sections</b>", S, "h2"))
    rpt_secs = [
        ("Executive Summary",
         "Six KPIs (Revenue, Avg Daily Revenue, Avg Food Cost %, Avg Labour Cost %, Prime Cost %, Net Cash Position) "
         "followed by data-driven insight bullets: revenue trend direction, food cost threshold status, "
         "best and worst revenue day of week."),
        ("Revenue & Sales Analysis",
         "Monthly revenue table (Revenue, Covers, Avg Check, Food Cost, Food Cost %) plus insights: "
         "day-of-week breakdown, average check size trend, total covers, and a recommendation "
         "targeting the weakest-performing day."),
        ("Labour & Payroll",
         "Department summary table (Employees, Total Hours, Gross Pay) and monthly labour cost "
         "table (Labour Cost, Revenue, Labour Cost %). Insights include blended hourly rate, "
         "highest-cost department, weekly payroll trend, and highest earner."),
        ("Food Cost & Inventory",
         "Monthly food cost table (Food Cost, Revenue, Food Cost %, Status) and top 10 menu items "
         "by revenue. Insights: days above target/warning thresholds, worst food cost day with "
         "revenue context, half-over-half cost trend, and low-margin item count."),
        ("Expense Analysis",
         "Category breakdown table (Total Spend, % of Total) and top 10 vendors. Insights: "
         "largest category and vendor, month-over-month expense change, and concentration risk "
         "flag if top 2 categories exceed 70% of total spend."),
        ("Cash Flow",
         "Monthly cash flow table (Inflows, Outflows, Net) with summary KPIs. Insights: "
         "net position with outflow ratio, count of negative-net days, and daily net trend."),
    ]
    for title, desc in rpt_secs:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(1))

    story.append(_sp(2))
    story.append(_tip("The PDF download generates the exact same content and insights as the "
                      "on-screen preview. Both use the same underlying computations.", S))
    story.append(PageBreak())
    return story


def _section10_account(S):
    story = []
    story.append(_section_banner("10. Account Settings", S))
    story.append(_sp(3))

    acct_secs = [
        ("Restaurant Profile",
         "Update your restaurant name (appears on all report headers and dashboard titles) "
         "and email address. Changes save immediately."),
        ("Change Password",
         "Enter current password, new password, and confirm. "
         "Minimum 6 characters. The current password is verified before the change is applied."),
        ("Account Information",
         "Read-only display of: Username, Data Mode (Live or Simulated), and Email on File."),
        ("QuickBooks OAuth Post-Connect Sync",
         "When the OAuth redirect lands back on the app, it automatically redirects to Account Settings "
         "and triggers an immediate sync. A success or error flash message reports the result."),
    ]
    for title, desc in acct_secs:
        story.append(P(f"<b>{title}</b>", S, "h3"))
        story.append(P(desc, S, "body_j"))
        story.append(_sp(2))

    story.append(PageBreak())
    return story


def _section11_db(S):
    story = []
    story.append(_section_banner("11. Database Tables Reference", S))
    story.append(_sp(3))
    story.append(P("All tables use PostgreSQL hosted on Supabase. Every business data table includes "
                   "a <b>username</b> column that partitions data per account — no user can access "
                   "another user's data.", S, "body_j"))
    story.append(_sp(4))

    # users
    story.append(P("<b>users</b> — Account credentials and integration tokens", S, "h2"))
    story.append(_three_col_table([
        ("username",          "TEXT PK",   "Unique login name chosen at registration."),
        ("password_hash",     "TEXT",      "bcrypt hash of the user's password."),
        ("restaurant_name",   "TEXT",      "Display name used on all reports and headers."),
        ("email",             "TEXT",      "Optional. Previously used for report delivery."),
        ("phone_number",      "TEXT",      "Optional. Reserved for future 2FA use."),
        ("use_simulated_data","BOOLEAN",   "TRUE if the account is in demo/simulated mode."),
        ("qb_realm_id",       "TEXT",      "QuickBooks company ID (realmId) from OAuth redirect."),
        ("qb_refresh_token",  "TEXT",      "QuickBooks OAuth refresh token. Encrypted at rest."),
        ("qb_banking_scope",  "BOOLEAN",   "TRUE if the banking scope was included in the OAuth grant."),
        ("oauth_state",       "TEXT",      "Temporary nonce used during OAuth flow for CSRF protection. Cleared after use."),
        ("last_sync_at",      "TIMESTAMP", "UTC timestamp of the most recent Sync Now execution."),
        ("last_sync_status",  "TEXT",      "Result of last sync: 'ok', 'demo', or error description."),
        ("sim_fallback_cleared","BOOLEAN", "Internal migration flag. TRUE = simulated data fallback has been cleared."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(4))

    # daily_sales
    story.append(P("<b>daily_sales</b> — Daily revenue and guest metrics from Toast POS", S, "h2"))
    story.append(_three_col_table([
        ("username",       "TEXT",    "Account owner. Foreign key to users."),
        ("date",           "DATE PK", "Trading date (YYYY-MM-DD)."),
        ("revenue",        "NUMERIC", "Total revenue for the day in dollars."),
        ("covers",         "INTEGER", "Number of guest covers (seated guests) for the day."),
        ("avg_check",      "NUMERIC", "Average check size = revenue ÷ covers."),
        ("food_cost",      "NUMERIC", "Total food cost in dollars for the day."),
        ("food_cost_pct",  "NUMERIC", "Food cost as a percentage of revenue for the day."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(4))

    # daily_labor
    story.append(P("<b>daily_labor</b> — Daily labour cost summary derived from Paychex data", S, "h2"))
    story.append(_three_col_table([
        ("username",    "TEXT",    "Account owner."),
        ("date",        "DATE PK", "Trading date."),
        ("labor_cost",  "NUMERIC", "Total labour cost (gross wages) for the day in dollars."),
        ("hours",       "NUMERIC", "Total hours worked across all employees for the day."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(2))
    story.append(_note("daily_labor rows are derived from weekly_payroll during the Paychex CSV "
                       "import. The weekly gross pay is distributed evenly across the 7 days of "
                       "each pay period to create daily estimates.", S))
    story.append(_sp(4))

    # weekly_payroll
    story.append(P("<b>weekly_payroll</b> — Employee-level payroll per pay period from Paychex", S, "h2"))
    story.append(_three_col_table([
        ("username",        "TEXT",    "Account owner."),
        ("week_start",      "DATE PK", "First day (Monday) of the pay period."),
        ("week_end",        "DATE",    "Last day (Sunday) of the pay period."),
        ("employee_id",     "TEXT",    "Paychex employee ID number."),
        ("employee_name",   "TEXT",    "Full name of the employee."),
        ("dept",            "TEXT",    "Department name as configured in Paychex."),
        ("role",            "TEXT",    "Job title / role as configured in Paychex."),
        ("employment_type", "TEXT",    "Full-Time, Part-Time, or Contractor."),
        ("regular_hours",   "NUMERIC", "Regular (non-overtime) hours worked in the week."),
        ("overtime_hours",  "NUMERIC", "Overtime hours worked (hours above threshold, typically 40/week)."),
        ("total_hours",     "NUMERIC", "regular_hours + overtime_hours."),
        ("gross_pay",       "NUMERIC", "Total gross wages paid for the week in dollars."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(4))

    # expenses
    story.append(P("<b>expenses</b> — Operating expense transactions from QuickBooks Online", S, "h2"))
    story.append(_three_col_table([
        ("username",    "TEXT",    "Account owner."),
        ("date",        "DATE",    "Transaction date."),
        ("vendor",      "TEXT",    "Vendor / payee name from QuickBooks."),
        ("category",    "TEXT",    "Expense category / account name from QuickBooks Chart of Accounts. 'Pending Review' for uncategorised bank feed items."),
        ("amount",      "NUMERIC", "Transaction amount in dollars."),
        ("description", "TEXT",    "Transaction memo or description from QuickBooks."),
        ("txn_id",      "TEXT PK", "QuickBooks transaction ID. Used as the primary key to prevent duplicates on re-sync."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(4))

    # cash_flow
    story.append(P("<b>cash_flow</b> — Daily cash flow summary from QuickBooks", S, "h2"))
    story.append(_three_col_table([
        ("username", "TEXT",    "Account owner."),
        ("date",     "DATE PK", "Date of the cash flow record."),
        ("inflow",   "NUMERIC", "Total cash received / deposited on this date."),
        ("outflow",  "NUMERIC", "Total cash paid out on this date."),
        ("net",      "NUMERIC", "inflow − outflow for the day."),
    ], S, headers=("Column", "Type", "Description")))
    story.append(_sp(4))

    # menu_items
    story.append(P("<b>menu_items</b> — Menu item performance from Toast POS Item Selections", S, "h2"))
    story.append(_three_col_table([
        ("username",      "TEXT",    "Account owner."),
        ("name",          "TEXT PK", "Menu item name as it appears in Toast."),
        ("category",      "TEXT",    "Menu category (e.g. Appetizers, Entrees, Beverages)."),
        ("price",         "NUMERIC", "Current menu price in dollars."),
        ("quantity_sold", "INTEGER", "Total number of units sold in the export period."),
        ("total_revenue", "NUMERIC", "Total revenue generated = price × quantity_sold (approximately)."),
        ("margin_pct",    "NUMERIC", "Gross margin percentage if provided in the Toast export; otherwise 0."),
    ], S, headers=("Column", "Type", "Description")))

    story.append(PageBreak())
    return story


def _section12_dataflow(S):
    story = []
    story.append(_section_banner("12. Data Flow Summary", S))
    story.append(_sp(3))
    story.append(P("The diagram below summarises how data moves from each source system into the "
                   "TableMetrics database and which dashboard pages consume it.", S, "body_j"))
    story.append(_sp(4))

    # Data flow table
    flow_data = [
        [Paragraph("Source System", S["tbl_hdr"]),
         Paragraph("Import Method", S["tbl_hdr"]),
         Paragraph("Database Tables Populated", S["tbl_hdr"]),
         Paragraph("Pages That Use It", S["tbl_hdr"])],
        [Paragraph("Toast POS", S["tbl_cell_b"]),
         Paragraph("Manual CSV upload — Sales Summary report", S["tbl_cell"]),
         Paragraph("daily_sales, hourly_sales", S["tbl_cell"]),
         Paragraph("Summary, Sales", S["tbl_cell"])],
        [Paragraph("Toast POS", S["tbl_cell_b"]),
         Paragraph("Manual CSV upload — Item Selections report", S["tbl_cell"]),
         Paragraph("menu_items", S["tbl_cell"]),
         Paragraph("Summary, Inventory, Sales, Reports", S["tbl_cell"])],
        [Paragraph("Paychex Flex", S["tbl_cell_b"]),
         Paragraph("Manual CSV upload — Payroll Labor Cost report", S["tbl_cell"]),
         Paragraph("weekly_payroll, daily_labor", S["tbl_cell"]),
         Paragraph("Summary, Payroll, Reports", S["tbl_cell"])],
        [Paragraph("QuickBooks Online", S["tbl_cell_b"]),
         Paragraph("OAuth 2.0 sync (manual via Sync Now or on first connect)", S["tbl_cell"]),
         Paragraph("expenses, cash_flow", S["tbl_cell"]),
         Paragraph("Summary, Spending, Reports", S["tbl_cell"])],
    ]
    flow_widths = [35*mm, 52*mm, 50*mm, 38*mm]
    flow_tbl = Table(flow_data, colWidths=flow_widths, repeatRows=1)
    flow_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ROW_ALT]),
        ("LINEBELOW",     (0,0), (-1,-1), 0.3, LIGHT_RULE),
        ("LINEBELOW",     (0,0), (-1,0), 1, GOLD),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    story.append(flow_tbl)
    story.append(_sp(5))

    story.append(P("<b>Sync & Merge Logic</b>", S, "h2"))
    merge_points = [
        "All CSV imports use an <b>upsert / merge</b> strategy — existing rows are updated, new rows are inserted, and no data is deleted. Re-uploading the same file is safe.",
        "The QuickBooks sync uses the <b>txn_id</b> field as a unique key to prevent duplicate transactions on repeated syncs.",
        "Weekly payroll records are keyed on <b>(username, week_start, employee_id)</b>. Uploading a new export for the same pay period updates the existing record.",
        "Daily sales are keyed on <b>(username, date)</b>. Uploading an overlapping date range will update those days with the new values.",
        "Menu items are keyed on <b>(username, name)</b>. Re-uploading updates price, quantity, and revenue for each item.",
        "After every import or sync, <b>st.cache_data.clear()</b> is called to force all cached queries to re-run with the latest data.",
    ]
    for point in merge_points:
        story.append(B(f"• {point}", S))
    story.append(_sp(4))

    story.append(P("<b>Caching</b>", S, "h2"))
    story.append(P("All database query functions are decorated with <b>@st.cache_data(ttl=300)</b> "
                   "(5-minute cache). This means repeated page navigations within a session do not "
                   "re-query the database on every render. The cache is cleared after any import, "
                   "sync, or user update action.", S, "body_j"))
    story.append(_sp(4))

    story.append(P("<b>Date Range Filtering</b>", S, "h2"))
    story.append(P("Most query functions accept optional <b>start_date</b> and <b>end_date</b> "
                   "parameters that are applied as SQL WHERE clauses before data is returned. "
                   "The exception is the Payroll page, which uses an <b>overlap filter</b>: "
                   "pay periods are included if their week_end ≥ start_date AND week_start ≤ end_date, "
                   "so a weekly pay period that spans a date boundary is not excluded.", S, "body_j"))
    story.append(_sp(4))

    story.append(_gold_rule())
    story.append(_sp(2))
    story.append(P(f"End of Document  ·  TableMetrics Application Overview & User Guide  ·  {TODAY}",
                   S, "small"))
    return story


# ── Build ─────────────────────────────────────────────────────────────────────
def build(output_path: str):
    buf = io.BytesIO()
    S   = _S()
    doc = _make_doc(buf)

    story = []
    story += _cover(S)
    story += _toc(S)
    story += _section1_overview(S)
    story += _section2_auth(S)
    story += _section3_controls(S)
    story += _section4_summary(S)
    story += _section5_spending(S)
    story += _section6_payroll(S)
    story += _section7_inventory(S)
    story += _section8_sales(S)
    story += _section9_reports(S)
    story += _section10_account(S)
    story += _section11_db(S)
    story += _section12_dataflow(S)

    doc.build(story)

    Path(output_path).write_bytes(buf.getvalue())
    print(f"Generated: {output_path}  ({Path(output_path).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "TableMetrics_App_Guide.pdf"
    build(out)
