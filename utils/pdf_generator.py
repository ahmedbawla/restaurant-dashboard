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
INSIGHT_BG = colors.HexColor("#FDFBF3")

PAGE_W, PAGE_H = A4
MARGIN    = 18 * mm
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
                                       leading=13, leftIndent=4),
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
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 7),
        ("TOPPADDING",    (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING",   (0, 0), (-1, 0), 6),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 6),
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
    """Row of KPI cards. kpis = [(label, value, badge_or_None), ...]"""
    cell_w = CONTENT_W / len(kpis)
    cells = []
    for label, value, badge in kpis:
        badge_str = f"<br/><font size='7' color='#6C757D'>{badge}</font>" if badge else ""
        cells.append([
            Paragraph(label.upper(), styles["kpi_label"]),
            Paragraph(f"{value}{badge_str}", styles["kpi_value"]),
        ])
    tbl = Table([cells], colWidths=[cell_w] * len(kpis))
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), ROW_ALT),
        ("LINEBELOW",     (0, 0), (-1, -1), 2, GOLD),
        ("LINEBEFORE",    (1, 0), (-1, -1), 0.5, LIGHT_RULE),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


def _insight_block(items: list[tuple[str, str]], styles: dict) -> Table:
    """
    Gold-left-bordered insight card matching the on-screen preview.
    Each item is (icon, text) where text may contain <strong>...</strong>.
    """
    def _clean(t: str) -> str:
        return (t.replace("<strong>", "<b>")
                 .replace("</strong>", "</b>")
                 .replace("<br>", "<br/>"))

    rows = []
    for icon, text in items:
        rows.append([Paragraph(f"{icon}  {_clean(text)}", styles["insight"])])

    tbl = Table(rows, colWidths=[CONTENT_W - 2 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), INSIGHT_BG),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, GOLD),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, LIGHT_RULE),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, LIGHT_RULE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ── Formatting helpers ────────────────────────────────────────────────────────

def _c(v: float) -> str:
    return f"${v:,.0f}"

def _p(v: float) -> str:
    return f"{v:.1f}%"

def _badge(v: float, target: float, warning: float) -> str:
    if v <= target:  return "● On Target"
    if v <= warning: return "▲ Attention"
    return "▼ Off Target"


# ── Header / footer callbacks ─────────────────────────────────────────────────

def _make_header_footer(rest_name: str, period_str: str, styles: dict):
    def _on_page(canvas, doc):
        canvas.saveState()
        w, h = A4

        canvas.setFillColor(NAVY_DARK)
        canvas.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
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
    buf = io.BytesIO()
    styles = _styles()

    rest_name  = user.get("restaurant_name", "Restaurant")
    period_str = f"{start_date} – {end_date}"

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=26 * mm, bottomMargin=18 * mm,
        title=f"{rest_name} — Performance Report",
        author=rest_name,
    )

    on_page = _make_header_footer(rest_name, period_str, styles)
    story: list = []

    ds  = daily_sales.copy()    if not daily_sales.empty    else pd.DataFrame()
    dl  = daily_labor.copy()    if not daily_labor.empty    else pd.DataFrame()
    wp  = weekly_payroll.copy() if not weekly_payroll.empty else pd.DataFrame()
    exp = expenses.copy()       if not expenses.empty       else pd.DataFrame()
    cf  = cash_flow.copy()      if not cash_flow.empty      else pd.DataFrame()
    mi  = menu_items.copy()     if not menu_items.empty     else pd.DataFrame()

    food_target   = thresholds.get("food_cost_pct_target",  30.0)
    food_warning  = thresholds.get("food_cost_pct_warning", 33.0)
    labor_target  = thresholds.get("labor_cost_pct_target",  30.0)
    labor_warning = thresholds.get("labor_cost_pct_warning", 33.0)
    prime_target  = thresholds.get("prime_cost_pct_target",  60.0)
    prime_warning = thresholds.get("prime_cost_pct_warning", 65.0)

    # ── Pre-compute shared KPIs ───────────────────────────────────────────────
    rev_total = float(ds["revenue"].sum())    if not ds.empty else 0.0
    rev_avg   = float(ds["revenue"].mean())   if not ds.empty else 0.0
    covers    = int(ds["covers"].sum())       if not ds.empty else 0
    avg_check = float(ds["avg_check"].mean()) if not ds.empty else 0.0
    avg_food  = float(ds["food_cost_pct"].mean()) if not ds.empty else 0.0

    labor_by_day = (dl.groupby("date")["labor_cost"].sum().reset_index()
                    if not dl.empty else pd.DataFrame(columns=["date", "labor_cost"]))
    merged = (labor_by_day.merge(ds[["date", "revenue"]], on="date", how="inner")
              if not ds.empty and not labor_by_day.empty else pd.DataFrame())
    avg_labor = float((merged["labor_cost"] / merged["revenue"] * 100).mean()) if not merged.empty else 0.0
    prime_avg = avg_food + avg_labor
    exp_total = float(exp["amount"].sum()) if not exp.empty else 0.0
    net_cash  = float(cf["net"].sum())     if not cf.empty  else 0.0

    # ── Executive Summary ─────────────────────────────────────────────────────
    if "executive" in sections:
        story += _section_header("Executive Summary", styles)

        kpis = [
            ("Revenue (Period)",   _c(rev_total),  None),
            ("Avg. Daily Revenue", _c(rev_avg),     None),
            ("Avg. Food Cost %",   _p(avg_food),   _badge(avg_food,  food_target,  food_warning)),
            ("Avg. Labour Cost %", _p(avg_labor),  _badge(avg_labor, labor_target, labor_warning)),
            ("Prime Cost %",       _p(prime_avg),  _badge(prime_avg, prime_target, prime_warning)),
            ("Net Cash Position",  _c(net_cash),   None),
        ]
        story.append(_kpi_grid(kpis[:3], styles))
        story.append(Spacer(1, 2 * mm))
        story.append(_kpi_grid(kpis[3:], styles))
        story.append(Spacer(1, 4 * mm))

        # Insights (mirrors preview)
        exec_ins = []
        if not ds.empty:
            if len(ds) >= 4:
                mid   = len(ds) // 2
                fh    = ds["revenue"].iloc[:mid].mean()
                sh    = ds["revenue"].iloc[mid:].mean()
                pct   = (sh - fh) / fh * 100
                if pct >= 5:
                    exec_ins.append(("📈", f"Revenue trended <b>up {pct:.1f}%</b> in the second half of the period vs the first half ({_c(fh)}/day → {_c(sh)}/day)."))
                elif pct <= -5:
                    exec_ins.append(("📉", f"Revenue trended <b>down {abs(pct):.1f}%</b> in the second half of the period ({_c(fh)}/day → {_c(sh)}/day). Investigate what changed mid-period."))
                else:
                    exec_ins.append(("➡️", f"Revenue was <b>relatively stable</b> across the period ({pct:+.1f}% half-over-half), averaging {_c(rev_avg)}/day."))

            days_above_wn  = int((ds["food_cost_pct"] > food_warning).sum())
            days_above_tgt = int((ds["food_cost_pct"] > food_target).sum())
            if days_above_wn > 0:
                exec_ins.append(("🔴", f"Food cost exceeded the {food_warning}% warning level on <b>{days_above_wn} day{'s' if days_above_wn != 1 else ''}</b>. Average for the period: {avg_food:.1f}%."))
            elif days_above_tgt > 0:
                exec_ins.append(("🟡", f"Food cost averaged <b>{avg_food:.1f}%</b> — above the {food_target}% target on {days_above_tgt} day{'s' if days_above_tgt != 1 else ''} this period."))
            else:
                exec_ins.append(("🟢", f"Food cost averaged <b>{avg_food:.1f}%</b> — within the {food_target}% target throughout the period."))

            ds_dow = ds.copy()
            ds_dow["day"]     = pd.to_datetime(ds_dow["date"]).dt.day_name()
            ds_dow["day_num"] = pd.to_datetime(ds_dow["date"]).dt.dayofweek
            dow_avg  = ds_dow.groupby(["day", "day_num"])["revenue"].mean()
            best_day  = dow_avg.idxmax()[0]
            worst_day = dow_avg.idxmin()[0]
            exec_ins.append(("🏆", f"<b>{best_day}</b> is your strongest day (avg {_c(dow_avg.max())}); <b>{worst_day}</b> is the weakest (avg {_c(dow_avg.min())})."))

        if exec_ins:
            story.append(_insight_block(exec_ins, styles))
        story.append(Spacer(1, 4 * mm))

    # ── Revenue & Sales ───────────────────────────────────────────────────────
    if "revenue" in sections and not ds.empty:
        story += _section_header("Revenue & Sales Analysis", styles)

        ds_copy = ds.copy()
        ds_copy["month"] = pd.to_datetime(ds_copy["date"]).dt.to_period("M").astype(str)
        monthly = ds_copy.groupby("month").agg(
            Revenue=("revenue","sum"), Covers=("covers","sum"),
            Avg_Check=("avg_check","mean"), Food_Cost=("food_cost","sum"),
            Food_Pct=("food_cost_pct","mean"),
        ).reset_index().sort_values("month", ascending=False)

        headers = ["Month", "Revenue", "Covers", "Avg. Check", "Food Cost", "Food Cost %"]
        col_w   = [30*mm, 32*mm, 25*mm, 28*mm, 30*mm, 30*mm]
        rows = [
            [r.month, _c(r.Revenue), f"{r.Covers:,.0f}",
             _c(r.Avg_Check), _c(r.Food_Cost), _p(r.Food_Pct)]
            for _, r in monthly.iterrows()
        ]
        story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2,3,4,5])]))
        story.append(Spacer(1, 4 * mm))

        # Insights
        rev_ins = []
        ds2 = ds.copy()
        ds2["day"]     = pd.to_datetime(ds2["date"]).dt.day_name()
        ds2["day_num"] = pd.to_datetime(ds2["date"]).dt.dayofweek
        dow_rev  = ds2.groupby(["day", "day_num"])["revenue"].mean()
        best_d   = dow_rev.idxmax()[0]
        worst_d  = dow_rev.idxmin()[0]
        rev_ins.append(("📅", f"By day of week, <b>{best_d}</b> averages the most revenue ({_c(dow_rev.max())}) and <b>{worst_d}</b> the least ({_c(dow_rev.min())})."))

        if len(ds) >= 14:
            mid = len(ds) // 2
            fh_chk = ds["avg_check"].iloc[:mid].mean()
            sh_chk = ds["avg_check"].iloc[mid:].mean()
            chk_chg = (sh_chk - fh_chk) / fh_chk * 100
            if chk_chg >= 2:
                rev_ins.append(("💳", f"Average check size grew <b>{chk_chg:.1f}%</b> across the period ({_c(fh_chk)} → {_c(sh_chk)}), indicating stronger spend per guest."))
            elif chk_chg <= -2:
                rev_ins.append(("💳", f"Average check size declined <b>{abs(chk_chg):.1f}%</b> ({_c(fh_chk)} → {_c(sh_chk)}). Review menu mix or whether discounting increased."))
            else:
                rev_ins.append(("💳", f"Average check size held steady at approximately {_c(ds['avg_check'].mean())} throughout the period."))

        avg_cov = ds["covers"].mean()
        rev_ins.append(("👥", f"<b>{covers:,} covers</b> served during the period, averaging <b>{avg_cov:,.0f}/day</b>."))
        rev_ins.append(("💡", f"<b>{worst_d}</b> consistently underperforms — consider targeted promotions or adjusted staffing on that day."))

        story.append(_insight_block(rev_ins, styles))
        story.append(Spacer(1, 4 * mm))

    # ── Labour & Payroll ──────────────────────────────────────────────────────
    if "labor" in sections and not dl.empty:
        story += _section_header("Labour & Payroll", styles)

        if not wp.empty:
            dept = (wp.groupby("dept")
                    .agg(Employees=("employee_id","nunique"),
                         Total_Hours=("total_hours","sum"),
                         Gross_Pay=("gross_pay","sum"))
                    .reset_index().sort_values("Gross_Pay", ascending=False))
            headers = ["Department", "Employees", "Total Hours", "Gross Pay"]
            col_w   = [55*mm, 32*mm, 40*mm, 48*mm]
            rows = [
                [r.dept, str(r.Employees), f"{r.Total_Hours:,.1f} hrs", _c(r.Gross_Pay)]
                for _, r in dept.iterrows()
            ]
            story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2,3])]))

        if not merged.empty:
            story.append(Spacer(1, 3 * mm))
            merged_copy = merged.copy()
            merged_copy["labor_pct"] = merged_copy["labor_cost"] / merged_copy["revenue"] * 100
            merged_copy["month"] = pd.to_datetime(merged_copy["date"]).dt.to_period("M").astype(str)
            monthly_l = (merged_copy.groupby("month")
                         .agg(Labor_Cost=("labor_cost","sum"), Revenue=("revenue","sum"))
                         .reset_index())
            monthly_l["Labor_Pct"] = monthly_l["Labor_Cost"] / monthly_l["Revenue"] * 100
            monthly_l = monthly_l.sort_values("month", ascending=False)
            headers = ["Month", "Labour Cost", "Revenue", "Labour Cost %"]
            col_w   = [35*mm, 40*mm, 40*mm, 40*mm]
            rows = [[r.month, _c(r.Labor_Cost), _c(r.Revenue), _p(r.Labor_Pct)]
                    for _, r in monthly_l.iterrows()]
            story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2,3])]))

        # Insights
        labor_ins = []
        if not wp.empty:
            total_pay = wp["gross_pay"].sum()
            total_hrs = wp["total_hours"].sum()
            avg_rate  = total_pay / total_hrs if total_hrs else 0.0
            labor_ins.append(("⏱️", f"Total payroll: <b>{_c(total_pay)}</b> across <b>{total_hrs:,.0f} hours</b> — blended rate of <b>{_c(avg_rate)}/hr</b>."))

            dept_pay  = wp.groupby("dept")["gross_pay"].sum()
            top_dept  = dept_pay.idxmax()
            top_dept_pct = dept_pay[top_dept] / dept_pay.sum() * 100
            labor_ins.append(("💼", f"<b>{top_dept}</b> is the highest payroll department — {top_dept_pct:.1f}% of total spend ({_c(dept_pay[top_dept])})."))

            wk_totals = wp.groupby("week_start")["gross_pay"].sum().sort_index()
            if len(wk_totals) >= 4:
                mid    = len(wk_totals) // 2
                fh_pay = wk_totals.iloc[:mid].mean()
                sh_pay = wk_totals.iloc[mid:].mean()
                pay_chg = (sh_pay - fh_pay) / fh_pay * 100
                if pay_chg >= 5:
                    labor_ins.append(("📈", f"Weekly payroll rose <b>{pay_chg:.1f}%</b> across the period ({_c(fh_pay)} → {_c(sh_pay)}/week). Review whether this reflects scheduled raises, new hires, or additional hours."))
                elif pay_chg <= -5:
                    labor_ins.append(("📉", f"Weekly payroll decreased <b>{abs(pay_chg):.1f}%</b> ({_c(fh_pay)} → {_c(sh_pay)}/week)."))
                else:
                    labor_ins.append(("➡️", f"Weekly payroll was consistent across the period, averaging <b>{_c(wk_totals.mean())}/week</b>."))

            top_earner = wp.groupby("employee_name")["gross_pay"].sum()
            labor_ins.append(("👤", f"Highest total earner for the period: <b>{top_earner.idxmax()}</b> at <b>{_c(top_earner.max())}</b>."))

        if labor_ins:
            story.append(Spacer(1, 3 * mm))
            story.append(_insight_block(labor_ins, styles))
        story.append(Spacer(1, 4 * mm))

    # ── Food Cost & Inventory ─────────────────────────────────────────────────
    if "food_cost" in sections and not ds.empty:
        story += _section_header("Food Cost & Inventory", styles)

        ds_copy2 = ds.copy()
        ds_copy2["month"] = pd.to_datetime(ds_copy2["date"]).dt.to_period("M").astype(str)
        monthly_f = ds_copy2.groupby("month").agg(
            Food_Cost=("food_cost","sum"), Revenue=("revenue","sum"),
            Food_Pct=("food_cost_pct","mean"),
        ).reset_index().sort_values("month", ascending=False)
        headers = ["Month", "Food Cost", "Revenue", "Food Cost %", "Status"]
        col_w   = [30*mm, 35*mm, 35*mm, 30*mm, 25*mm]
        rows = [
            [r.month, _c(r.Food_Cost), _c(r.Revenue), _p(r.Food_Pct),
             "✓" if r.Food_Pct <= food_target else ("!" if r.Food_Pct <= food_warning else "✗")]
            for _, r in monthly_f.iterrows()
        ]
        story.append(_data_table(headers, rows, col_w, right_align_cols=[1,2,3]))

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
            story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[2,3,4,5])]))

        # Insights
        food_ins = []
        days_above_tgt = int((ds["food_cost_pct"] > food_target).sum())
        days_above_wn  = int((ds["food_cost_pct"] > food_warning).sum())
        total_days     = len(ds)

        if days_above_wn > 0:
            food_ins.append(("🔴", f"Food cost exceeded the {food_warning}% warning threshold on <b>{days_above_wn} of {total_days} days</b>. Pinpoint those dates and review purchasing, waste logs, or spoilage."))
        elif days_above_tgt > 0:
            food_ins.append(("🟡", f"Food cost averaged <b>{avg_food:.1f}%</b> and was above the {food_target}% target on <b>{days_above_tgt} of {total_days} days</b> ({days_above_tgt/total_days*100:.0f}% of the period)."))
        else:
            food_ins.append(("🟢", f"Food cost averaged <b>{avg_food:.1f}%</b> and stayed within the {food_target}% target on every day in the period."))

        worst_row = ds.loc[ds["food_cost_pct"].idxmax()]
        food_ins.append(("📍", f"Highest food cost day: <b>{worst_row['date']}</b> at <b>{worst_row['food_cost_pct']:.1f}%</b> on revenue of {_c(worst_row['revenue'])}. Investigate purchasing or waste events on that date."))

        if len(ds) >= 14:
            mid   = len(ds) // 2
            fh_fc = ds["food_cost_pct"].iloc[:mid].mean()
            sh_fc = ds["food_cost_pct"].iloc[mid:].mean()
            fc_chg = sh_fc - fh_fc
            if fc_chg >= 1.0:
                food_ins.append(("📈", f"Food cost trended higher in the second half ({fh_fc:.1f}% → {sh_fc:.1f}%). Review whether input costs rose or portion control slipped."))
            elif fc_chg <= -1.0:
                food_ins.append(("📉", f"Food cost improved in the second half ({fh_fc:.1f}% → {sh_fc:.1f}%), suggesting purchasing or waste controls are working."))

        if not mi.empty:
            top_item   = mi.loc[mi["total_revenue"].idxmax()]
            low_margin = mi[mi["margin_pct"] < mi["margin_pct"].median()]
            food_ins.append(("🍽️", f"Top revenue item: <b>{top_item['name']}</b> ({_c(top_item['total_revenue'])}, {int(top_item['quantity_sold']):,} sold)."))
            if not low_margin.empty:
                food_ins.append(("💡", f"<b>{len(low_margin)} menu item{'s' if len(low_margin) != 1 else ''}</b> are below the median margin. Review pricing or ingredient costs on those items."))

        story.append(Spacer(1, 3 * mm))
        story.append(_insight_block(food_ins, styles))
        story.append(Spacer(1, 4 * mm))

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
        story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2])]))
        story.append(Spacer(1, 3 * mm))

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
        story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2])]))

        # Insights
        exp_ins = []
        cat_totals   = exp.groupby("category")["amount"].sum().sort_values(ascending=False)
        top_cat      = cat_totals.index[0]
        top_cat_pct  = cat_totals.iloc[0] / exp_total * 100
        vendor_totals = exp.groupby("vendor")["amount"].sum().sort_values(ascending=False)
        top_vendor    = vendor_totals.index[0]

        exp_ins.append(("📦", f"<b>{top_cat}</b> is the largest expense category at <b>{_c(cat_totals.iloc[0])}</b> ({top_cat_pct:.1f}% of total spend)."))
        exp_ins.append(("🏪", f"<b>{top_vendor}</b> is your largest vendor at <b>{_c(vendor_totals.iloc[0])}</b>. Consider whether consolidation in {top_cat} could improve pricing."))

        exp_copy = exp.copy()
        exp_copy["month"] = pd.to_datetime(exp_copy["date"]).dt.to_period("M").astype(str)
        monthly_exp = exp_copy.groupby("month")["amount"].sum().sort_index()
        if len(monthly_exp) >= 2:
            fh_exp  = monthly_exp.iloc[0]
            sh_exp  = monthly_exp.iloc[-1]
            exp_chg = (sh_exp - fh_exp) / fh_exp * 100
            if exp_chg >= 5:
                exp_ins.append(("📈", f"Expenses rose <b>{exp_chg:.1f}%</b> from {monthly_exp.index[0]} ({_c(fh_exp)}) to {monthly_exp.index[-1]} ({_c(sh_exp)}). Verify this aligns with revenue growth."))
            elif exp_chg <= -5:
                exp_ins.append(("📉", f"Expenses decreased <b>{abs(exp_chg):.1f}%</b> from {monthly_exp.index[0]} to {monthly_exp.index[-1]} — a positive efficiency trend."))

        if len(cat_totals) >= 2:
            top2_pct = (cat_totals.iloc[0] + cat_totals.iloc[1]) / exp_total * 100
            if top2_pct > 70:
                exp_ins.append(("⚠️", f"Top 2 categories (<b>{cat_totals.index[0]}</b> and <b>{cat_totals.index[1]}</b>) account for <b>{top2_pct:.0f}%</b> of all expenses — cost shocks in these areas have outsized impact."))

        story.append(Spacer(1, 3 * mm))
        story.append(_insight_block(exp_ins, styles))
        story.append(Spacer(1, 4 * mm))

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    if "cash_flow" in sections and not cf.empty:
        story += _section_header("Cash Flow", styles)

        cf_copy = cf.copy()
        cf_copy["month"] = pd.to_datetime(cf_copy["date"]).dt.to_period("M").astype(str)
        monthly_cf = cf_copy.groupby("month").agg(
            Inflow=("inflow","sum"), Outflow=("outflow","sum"), Net=("net","sum"),
        ).reset_index().sort_values("month", ascending=False)
        headers = ["Month", "Inflows", "Outflows", "Net Cash Flow"]
        col_w   = [35*mm, 40*mm, 40*mm, 40*mm]
        rows = [[r.month, _c(r.Inflow), _c(r.Outflow), _c(r.Net)]
                for _, r in monthly_cf.iterrows()]
        story.append(KeepTogether([_data_table(headers, rows, col_w, right_align_cols=[1,2,3])]))

        # Summary KPIs
        story.append(Spacer(1, 3 * mm))
        cf_kpis = [
            ("Total Inflows",  _c(cf["inflow"].sum()),  None),
            ("Total Outflows", _c(cf["outflow"].sum()), None),
            ("Net Position",   _c(net_cash),            None),
        ]
        story.append(_kpi_grid(cf_kpis, styles))

        # Insights
        cf_ins = []
        total_in  = cf["inflow"].sum()
        total_out = cf["outflow"].sum()
        neg_days  = int((cf["net"] < 0).sum())
        total_cf_days = len(cf)
        ratio = total_out / total_in * 100 if total_in else 0.0

        if net_cash >= 0:
            cf_ins.append(("🟢", f"Net cash position for the period is <b>{_c(net_cash)}</b> — positive overall. Outflows represent <b>{ratio:.1f}%</b> of inflows."))
        else:
            cf_ins.append(("🔴", f"Net cash position is <b>{_c(net_cash)}</b> — <b>negative for the period</b>. Outflows exceeded inflows by {_c(abs(net_cash))}. Review largest outflow categories."))

        if neg_days > 0:
            cf_ins.append(("⚠️", f"Cash flow was negative on <b>{neg_days} of {total_cf_days} days</b> ({neg_days/total_cf_days*100:.0f}% of the period). Identify whether these cluster around specific days or month-end payment cycles."))
        else:
            cf_ins.append(("✅", "Cash flow was positive on every day in the period — no negative-net days recorded."))

        if len(cf) >= 14:
            mid    = len(cf) // 2
            fh_net = cf["net"].iloc[:mid].mean()
            sh_net = cf["net"].iloc[mid:].mean()
            if sh_net > fh_net * 1.10:
                cf_ins.append(("📈", f"Daily net cash improved from an average of <b>{_c(fh_net)}</b> in the first half to <b>{_c(sh_net)}</b> in the second half."))
            elif sh_net < fh_net * 0.90:
                cf_ins.append(("📉", f"Daily net cash declined from <b>{_c(fh_net)}</b> (first half) to <b>{_c(sh_net)}</b> (second half). Monitor whether this is seasonal or structural."))

        story.append(Spacer(1, 3 * mm))
        story.append(_insight_block(cf_ins, styles))
        story.append(Spacer(1, 4 * mm))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
