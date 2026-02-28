"""
PDF report generator using ReportLab.
Returns raw bytes suitable for st.download_button.
"""

import io
from datetime import date as dt_date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#1B4F72")
NAVY_DARK = colors.HexColor("#154360")
GOLD      = colors.HexColor("#D4A84B")
GREEN     = colors.HexColor("#1E8449")
RED       = colors.HexColor("#C0392B")
AMBER     = colors.HexColor("#D68910")
ROW_ALT   = colors.HexColor("#F4F6F9")
ROW_WHITE = colors.white
LIGHT_RULE = colors.HexColor("#DDE1E7")
TEXT_DARK  = colors.HexColor("#1A1A2A")
TEXT_GREY  = colors.HexColor("#6C757D")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ── Style helpers ─────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    return {
        "restaurant": ParagraphStyle("restaurant", fontName="Helvetica-Bold",
                                     fontSize=22, textColor=colors.white,
                                     leading=26, spaceAfter=2),
        "report_title": ParagraphStyle("report_title", fontName="Helvetica",
                                       fontSize=13, textColor=colors.HexColor("#BDC3C7"),
                                       spaceAfter=2),
        "report_meta":  ParagraphStyle("report_meta", fontName="Helvetica",
                                       fontSize=9, textColor=colors.HexColor("#AEB6BF")),
        "section":      ParagraphStyle("section", fontName="Helvetica-Bold",
                                       fontSize=9, textColor=colors.white,
                                       letterSpacing=1.5, spaceAfter=0),
        "label":        ParagraphStyle("label", fontName="Helvetica-Bold",
                                       fontSize=7, textColor=TEXT_GREY,
                                       letterSpacing=1, leading=10),
        "kpi_value":    ParagraphStyle("kpi_value", fontName="Helvetica-Bold",
                                       fontSize=18, textColor=NAVY, leading=22),
        "kpi_label":    ParagraphStyle("kpi_label", fontName="Helvetica-Bold",
                                       fontSize=7, textColor=TEXT_GREY,
                                       letterSpacing=1.2, leading=9),
        "body":         ParagraphStyle("body", fontName="Helvetica",
                                       fontSize=8, textColor=TEXT_DARK, leading=11),
        "footer":       ParagraphStyle("footer", fontName="Helvetica",
                                       fontSize=7, textColor=TEXT_GREY,
                                       alignment=TA_CENTER, leading=9),
        "insight":      ParagraphStyle("insight", fontName="Helvetica",
                                       fontSize=8.5, textColor=TEXT_DARK,
                                       leading=13, leftIndent=10),
    }


def _section_header(title: str, styles: dict) -> list:
    """Navy band with white section title."""
    hdr = Table(
        [[Paragraph(title.upper(), styles["section"])]],
        colWidths=[CONTENT_W],
        rowHeights=[14 * mm],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, GOLD),
    ]))
    return [hdr, Spacer(1, 3 * mm)]


def _data_table(headers: list, rows: list[list], col_widths: list,
                right_align_cols: list | None = None) -> Table:
    """Styled data table with alternating row shading."""
    data = [headers] + rows
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 7),
        ("LETTERSPACNG",  (0, 0), (-1, 0), 1),
        ("TOPPADDING",    (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING",   (0, 0), (-1, 0), 6),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 6),
        # Data rows
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",   (0, 1), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 1), (-1, -1), 6),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [ROW_WHITE, ROW_ALT]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, LIGHT_RULE),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.75, GOLD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, 0),  "LEFT"),
    ]
    for col in (right_align_cols or []):
        style_cmds.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
        style_cmds.append(("ALIGN", (col, 0), (col, 0), "RIGHT"))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _kpi_grid(kpis: list[tuple[str, str, str | None]], styles: dict) -> Table:
    """
    Render a row of KPI cards.
    kpis = [(label, value, badge_text_or_None), ...]
    """
    cell_w = CONTENT_W / len(kpis)
    cells = []
    for label, value, badge in kpis:
        badge_str = f"<br/><font size='7' color='#6C757D'>{badge}</font>" if badge else ""
        cell = [
            Paragraph(label.upper(), styles["kpi_label"]),
            Paragraph(f"{value}{badge_str}", styles["kpi_value"]),
        ]
        cells.append(cell)
    tbl = Table([cells], colWidths=[cell_w] * len(kpis))
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT),
        ("LINEBELOW",  (0, 0), (-1, -1), 2, GOLD),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.5, LIGHT_RULE),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


# ── Formatting helpers ────────────────────────────────────────────────────────

def _c(v: float) -> str:
    return f"${v:,.0f}"

def _p(v: float) -> str:
    return f"{v:.1f}%"

def _badge(v: float, target: float, warning: float) -> str:
    if v <= target:   return "● On Target"
    if v <= warning:  return "▲ Attention"
    return "▼ Off Target"


# ── Header / footer callbacks ─────────────────────────────────────────────────

def _make_header_footer(rest_name: str, period_str: str, styles: dict):
    def _on_page(canvas, doc):
        canvas.saveState()
        w, h = A4

        # ── Header band ──────────────────────────────────────────────────────
        canvas.setFillColor(NAVY_DARK)
        canvas.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
        # Gold underline
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 22 * mm, w, 1.2 * mm, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(MARGIN, h - 10 * mm, rest_name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#BDC3C7"))
        canvas.drawString(MARGIN, h - 16 * mm, f"Performance Report  ·  {period_str}")
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(GOLD)
        canvas.drawRightString(w - MARGIN, h - 13 * mm, "CONFIDENTIAL")

        # ── Footer ────────────────────────────────────────────────────────────
        canvas.setFillColor(LIGHT_RULE)
        canvas.rect(MARGIN, 10 * mm, w - 2 * MARGIN, 0.3 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT_GREY)
        canvas.drawString(MARGIN, 6.5 * mm,
                          f"Confidential — For Authorised Recipients Only  ·  {rest_name}")
        canvas.drawRightString(w - MARGIN, 6.5 * mm,
                               f"Page {doc.page}  ·  Generated {dt_date.today().strftime('%B %d, %Y')}")
        canvas.restoreState()
    return _on_page


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pdf(
    user: dict,
    daily_sales: pd.DataFrame,
    daily_labor: pd.DataFrame,
    weekly_payroll: pd.DataFrame,
    expenses: pd.DataFrame,
    cash_flow: pd.DataFrame,
    menu_items: pd.DataFrame,
    sections: list[str],
    thresholds: dict,
    start_date: str,
    end_date: str,
) -> bytes:
    """
    Generate a professional A4 PDF report and return raw bytes.
    """
    buf = io.BytesIO()
    styles = _styles()

    rest_name  = user.get("restaurant_name", "Restaurant")
    period_str = f"{start_date} – {end_date}"

    TOP_MARGIN = 26 * mm   # leave room for the header band

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=18 * mm,
        title=f"{rest_name} — Performance Report",
        author=rest_name,
    )

    on_page = _make_header_footer(rest_name, period_str, styles)
    story: list = []

    ds  = daily_sales.copy()  if not daily_sales.empty  else pd.DataFrame()
    dl  = daily_labor.copy()  if not daily_labor.empty  else pd.DataFrame()
    wp  = weekly_payroll.copy() if not weekly_payroll.empty else pd.DataFrame()
    exp = expenses.copy()     if not expenses.empty     else pd.DataFrame()
    cf  = cash_flow.copy()    if not cash_flow.empty    else pd.DataFrame()
    mi  = menu_items.copy()   if not menu_items.empty   else pd.DataFrame()

    food_target  = thresholds.get("food_cost_pct_target",  30.0)
    food_warning = thresholds.get("food_cost_pct_warning", 33.0)
    labor_target  = thresholds.get("labor_cost_pct_target",  30.0)
    labor_warning = thresholds.get("labor_cost_pct_warning", 33.0)
    prime_target  = thresholds.get("prime_cost_pct_target",  60.0)
    prime_warning = thresholds.get("prime_cost_pct_warning", 65.0)

    # ── Pre-compute KPIs ──────────────────────────────────────────────────────
    rev_total = float(ds["revenue"].sum())    if not ds.empty else 0.0
    rev_avg   = float(ds["revenue"].mean())   if not ds.empty else 0.0
    covers    = int(ds["covers"].sum())       if not ds.empty else 0
    avg_check = float(ds["avg_check"].mean()) if not ds.empty else 0.0
    avg_food  = float(ds["food_cost_pct"].mean()) if not ds.empty else 0.0
    tot_food  = float(ds["food_cost"].sum())  if not ds.empty else 0.0

    labor_by_day = (dl.groupby("date")["labor_cost"].sum().reset_index()
                    if not dl.empty else pd.DataFrame(columns=["date", "labor_cost"]))
    merged = (labor_by_day.merge(ds[["date", "revenue"]], on="date", how="inner")
              if not ds.empty and not labor_by_day.empty else pd.DataFrame())
    avg_labor = float((merged["labor_cost"] / merged["revenue"] * 100).mean()) if not merged.empty else 0.0
    tot_labor = float(labor_by_day["labor_cost"].sum()) if not labor_by_day.empty else 0.0

    prime_avg = avg_food + avg_labor
    exp_total = float(exp["amount"].sum()) if not exp.empty else 0.0
    net_cash  = float(cf["net"].sum())     if not cf.empty else 0.0

    # ── Executive Summary ─────────────────────────────────────────────────────
    if "executive" in sections:
        story += _section_header("Executive Summary", styles)

        kpis = [
            ("Revenue (Period)",   _c(rev_total),   None),
            ("Avg. Daily Revenue", _c(rev_avg),      None),
            ("Avg. Food Cost %",   _p(avg_food),    _badge(avg_food,  food_target,  food_warning)),
            ("Avg. Labour Cost %", _p(avg_labor),   _badge(avg_labor, labor_target, labor_warning)),
            ("Prime Cost %",       _p(prime_avg),   _badge(prime_avg, prime_target, prime_warning)),
            ("Net Cash Position",  _c(net_cash),    None),
        ]
        story.append(_kpi_grid(kpis[:3], styles))
        story.append(Spacer(1, 2 * mm))
        story.append(_kpi_grid(kpis[3:], styles))
        story.append(Spacer(1, 4 * mm))

        # Narrative insights
        insights = [
            f"Revenue for the period totalled <b>{_c(rev_total)}</b> across "
            f"<b>{len(ds):,}</b> trading days (avg. <b>{_c(rev_avg)}</b>/day).",
            f"Guest covers totalled <b>{covers:,}</b> with an average check size of <b>{_c(avg_check)}</b>.",
            f"Food cost averaged <b>{_p(avg_food)}</b> — "
            + ("on target" if avg_food <= food_target else
               "within warning range" if avg_food <= food_warning else "above target")
            + f" (target ≤{food_target:.0f}%).",
            f"Labour cost averaged <b>{_p(avg_labor)}</b> — "
            + ("on target" if avg_labor <= labor_target else
               "within warning range" if avg_labor <= labor_warning else "above target")
            + f" (target ≤{labor_target:.0f}%).",
            f"Prime cost (food + labour) averaged <b>{_p(prime_avg)}</b> "
            + ("— within target range." if prime_avg <= prime_target else "— above target threshold."),
        ]
        for txt in insights:
            story.append(Paragraph(f"• &nbsp; {txt}", styles["insight"]))
            story.append(Spacer(1, 1.5 * mm))
        story.append(Spacer(1, 4 * mm))

    # ── Revenue & Sales ───────────────────────────────────────────────────────
    if "revenue" in sections and not ds.empty:
        story += _section_header("Revenue & Sales Analysis", styles)

        # Monthly summary
        ds_copy = ds.copy()
        ds_copy["month"] = pd.to_datetime(ds_copy["date"]).dt.to_period("M").astype(str)
        monthly = ds_copy.groupby("month").agg(
            Revenue=("revenue", "sum"),
            Covers=("covers", "sum"),
            Avg_Check=("avg_check", "mean"),
            Food_Cost=("food_cost", "sum"),
            Food_Pct=("food_cost_pct", "mean"),
        ).reset_index().sort_values("month", ascending=False)

        headers = ["Month", "Revenue", "Covers", "Avg. Check", "Food Cost", "Food Cost %"]
        col_w   = [30*mm, 32*mm, 25*mm, 28*mm, 30*mm, 30*mm]
        rows = [
            [r.month, _c(r.Revenue), f"{r.Covers:,.0f}",
             _c(r.Avg_Check), _c(r.Food_Cost), _p(r.Food_Pct)]
            for _, r in monthly.iterrows()
        ]
        story.append(KeepTogether([
            _data_table(headers, rows, col_w, right_align_cols=[1, 2, 3, 4, 5]),
        ]))
        story.append(Spacer(1, 5 * mm))

    # ── Labour & Payroll ──────────────────────────────────────────────────────
    if "labor" in sections and not dl.empty:
        story += _section_header("Labour & Payroll", styles)

        # Department breakdown
        if not wp.empty:
            dept = (wp.groupby("dept")
                    .agg(Employees=("employee_id","nunique"),
                         Total_Hours=("total_hours","sum"),
                         OT_Hours=("overtime_hours","sum"),
                         Gross_Pay=("gross_pay","sum"))
                    .reset_index().sort_values("Gross_Pay", ascending=False))
            headers = ["Department", "Employees", "Total Hours", "Overtime Hours", "Gross Pay"]
            col_w   = [45*mm, 28*mm, 32*mm, 35*mm, 35*mm]
            rows = [
                [r.dept, str(r.Employees), f"{r.Total_Hours:,.1f} hrs",
                 f"{r.OT_Hours:,.1f} hrs", _c(r.Gross_Pay)]
                for _, r in dept.iterrows()
            ]
            story.append(KeepTogether([
                _data_table(headers, rows, col_w, right_align_cols=[1, 2, 3, 4]),
            ]))

        # Labour cost % by period
        if not merged.empty:
            story.append(Spacer(1, 3 * mm))
            merged_copy = merged.copy()
            merged_copy["labor_pct"] = merged_copy["labor_cost"] / merged_copy["revenue"] * 100
            merged_copy["month"] = pd.to_datetime(merged_copy["date"]).dt.to_period("M").astype(str)
            monthly_l = merged_copy.groupby("month").agg(
                Labor_Cost=("labor_cost","sum"),
                Revenue=("revenue","sum"),
            ).reset_index()
            monthly_l["Labor_Pct"] = monthly_l["Labor_Cost"] / monthly_l["Revenue"] * 100
            monthly_l = monthly_l.sort_values("month", ascending=False)
            headers = ["Month", "Labour Cost", "Revenue", "Labour Cost %"]
            col_w   = [35*mm, 40*mm, 40*mm, 40*mm]
            rows = [
                [r.month, _c(r.Labor_Cost), _c(r.Revenue), _p(r.Labor_Pct)]
                for _, r in monthly_l.iterrows()
            ]
            story.append(KeepTogether([
                _data_table(headers, rows, col_w, right_align_cols=[1, 2, 3]),
            ]))
        story.append(Spacer(1, 5 * mm))

    # ── Food Cost & Inventory ─────────────────────────────────────────────────
    if "food_cost" in sections and not ds.empty:
        story += _section_header("Food Cost & Inventory", styles)

        # Monthly food cost
        ds_copy2 = ds.copy()
        ds_copy2["month"] = pd.to_datetime(ds_copy2["date"]).dt.to_period("M").astype(str)
        monthly_f = ds_copy2.groupby("month").agg(
            Food_Cost=("food_cost","sum"),
            Revenue=("revenue","sum"),
            Food_Pct=("food_cost_pct","mean"),
        ).reset_index().sort_values("month", ascending=False)
        headers = ["Month", "Food Cost", "Revenue", "Food Cost %", "Status"]
        col_w   = [30*mm, 35*mm, 35*mm, 30*mm, 25*mm]
        rows = [
            [r.month, _c(r.Food_Cost), _c(r.Revenue), _p(r.Food_Pct),
             "✓" if r.Food_Pct <= food_target else ("!" if r.Food_Pct <= food_warning else "✗")]
            for _, r in monthly_f.iterrows()
        ]
        story.append(_data_table(headers, rows, col_w, right_align_cols=[1, 2, 3]))

        # Top menu items
        if not mi.empty:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("Top 10 Menu Items by Revenue", styles["label"]))
            story.append(Spacer(1, 1 * mm))
            top10 = mi.nlargest(10, "total_revenue")
            headers = ["Item", "Category", "Qty Sold", "Menu Price", "Margin %", "Revenue"]
            col_w   = [45*mm, 28*mm, 22*mm, 25*mm, 22*mm, 28*mm]
            rows = [
                [r["name"], r["category"], f"{r['quantity_sold']:,}",
                 f"${r['price']:.2f}", _p(r["margin_pct"]), _c(r["total_revenue"])]
                for _, r in top10.iterrows()
            ]
            story.append(KeepTogether([
                _data_table(headers, rows, col_w, right_align_cols=[2, 3, 4, 5]),
            ]))
        story.append(Spacer(1, 5 * mm))

    # ── Expense Analysis ──────────────────────────────────────────────────────
    if "expenses" in sections and not exp.empty:
        story += _section_header("Expense Analysis", styles)

        cat = (exp.groupby("category")["amount"]
               .sum().reset_index().sort_values("amount", ascending=False))
        headers = ["Category", "Total Spend", "% of Total"]
        col_w   = [70*mm, 50*mm, 35*mm]
        rows = [
            [r["category"], _c(r["amount"]), _p(r["amount"] / exp_total * 100)]
            for _, r in cat.iterrows()
        ]
        story.append(KeepTogether([
            _data_table(headers, rows, col_w, right_align_cols=[1, 2]),
        ]))
        story.append(Spacer(1, 3 * mm))

        # Top vendors
        vendors = (exp.groupby("vendor")["amount"]
                   .sum().reset_index().sort_values("amount", ascending=False).head(10))
        story.append(Paragraph("Top 10 Vendors by Spend", styles["label"]))
        story.append(Spacer(1, 1 * mm))
        headers = ["Vendor", "Total Spend", "% of Total"]
        col_w   = [70*mm, 50*mm, 35*mm]
        rows = [
            [r["vendor"], _c(r["amount"]), _p(r["amount"] / exp_total * 100)]
            for _, r in vendors.iterrows()
        ]
        story.append(KeepTogether([
            _data_table(headers, rows, col_w, right_align_cols=[1, 2]),
        ]))
        story.append(Spacer(1, 5 * mm))

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    if "cash_flow" in sections and not cf.empty:
        story += _section_header("Cash Flow", styles)

        # Monthly cash flow
        cf_copy = cf.copy()
        cf_copy["month"] = pd.to_datetime(cf_copy["date"]).dt.to_period("M").astype(str)
        monthly_cf = cf_copy.groupby("month").agg(
            Inflow=("inflow","sum"), Outflow=("outflow","sum"), Net=("net","sum"),
        ).reset_index().sort_values("month", ascending=False)
        headers = ["Month", "Inflows", "Outflows", "Net Cash Flow"]
        col_w   = [35*mm, 40*mm, 40*mm, 40*mm]
        rows = [
            [r.month, _c(r.Inflow), _c(r.Outflow), _c(r.Net)]
            for _, r in monthly_cf.iterrows()
        ]
        story.append(KeepTogether([
            _data_table(headers, rows, col_w, right_align_cols=[1, 2, 3]),
        ]))
        story.append(Spacer(1, 5 * mm))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
