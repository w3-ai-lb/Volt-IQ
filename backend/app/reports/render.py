"""
Report renderers, turn a ReportData into a downloadable PDF or Excel file.

Kept separate from builder.py so a new report type needs no renderer changes
and a new format needs no query changes.

Both renderers return raw bytes, which the router streams back with the right
Content-Type and Content-Disposition headers.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reports.builder import ReportData

def _fmt(value) -> str:
    """
    Human-readable cell text.

    Integers get thousands separators with no decimals (a count of 119 payments
    should not read "119.00"); floats get two decimals.
    """
    if isinstance(value, bool) or value is None:
        return "" if value is None else str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


BRAND = colors.HexColor("#2563eb")
INK = colors.HexColor("#131a28")
MUTED = colors.HexColor("#5b6880")
RULE = colors.HexColor("#dfe5f0")
BAND = colors.HexColor("#f2f6fc")

COMPANY = "NXTTRN"
PLATFORM = "AI-Powered Energy Analytics and Customer Engagement Platform"

# Excel: a professional face throughout, per the house style for spreadsheets.
XL_FONT = "Arial"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _pdf_header_footer(canvas, doc):
    """Brand bar on every page plus a page number in the footer."""
    canvas.saveState()
    width, height = doc.pagesize

    canvas.setFillColor(BRAND)
    canvas.rect(0, height - 12 * mm, width, 12 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(15 * mm, height - 8 * mm, COMPANY)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - 15 * mm, height - 8 * mm, PLATFORM)

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 10 * mm,
                      f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    canvas.drawRightString(width - 15 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def to_pdf(report: ReportData) -> bytes:
    """Render the report as a landscape A4 PDF."""
    buffer = io.BytesIO()
    # Landscape: these tables are wide, and wrapping columns hurts readability.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"{report.title}, {report.date_from} to {report.date_to}",
        author=COMPANY,
        subject=report.description,
    )

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontSize=17, leading=21,
                        textColor=INK, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5, leading=13,
                         textColor=MUTED, spaceAfter=10)
    lbl = ParagraphStyle("lbl", parent=base["Normal"], fontSize=8, leading=10,
                         textColor=MUTED, alignment=TA_LEFT)
    val = ParagraphStyle("val", parent=base["Normal"], fontSize=12.5, leading=15,
                         textColor=INK, fontName="Helvetica-Bold")
    cell = ParagraphStyle("cell", parent=base["Normal"], fontSize=8, leading=10)
    note = ParagraphStyle("note", parent=base["Normal"], fontSize=8, leading=11,
                          textColor=MUTED, spaceBefore=8)

    story: list = [
        Paragraph(report.title, h1),
        Paragraph(f"{report.description} &nbsp;·&nbsp; "
                  f"{report.date_from.strftime('%d %b %Y')} to "
                  f"{report.date_to.strftime('%d %b %Y')}", sub),
    ]

    # --- Summary tiles -----------------------------------------------------
    if report.summary:
        tiles = [[Paragraph(label, lbl) for label, _ in report.summary],
                 [Paragraph(value, val) for _, value in report.summary]]
        tile_table = Table(tiles, colWidths=[doc.width / len(report.summary)] * len(report.summary))
        tile_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BAND),
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [tile_table, Spacer(1, 14)]

    # --- Data table --------------------------------------------------------
    if report.rows:
        header = [Paragraph(f"<b>{c}</b>", cell) for c in report.columns]
        body = [[Paragraph(_fmt(v), cell) for v in row] for row in report.rows]

        totals: list = []
        if report.numeric_columns:
            totals = ["" for _ in report.columns]
            totals[0] = "TOTAL"
            for index in report.numeric_columns:
                values = [r[index] for r in report.rows
                          if isinstance(r[index], (int, float)) and not isinstance(r[index], bool)]
                # Keep the column's own type so a count totals as a count.
                column_sum = sum(values)
                if values and all(isinstance(v, int) for v in values):
                    column_sum = int(column_sum)
                totals[index] = _fmt(column_sum)
            totals = [Paragraph(f"<b>{v}</b>", cell) for v in totals]

        data = [header] + body + ([totals] if totals else [])
        table = Table(data, repeatRows=1, colWidths=[doc.width / len(report.columns)] * len(report.columns))

        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, RULE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, len(body)), [colors.white, BAND]),
        ]
        if totals:
            style += [
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eef9")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND),
            ]
        table.setStyle(TableStyle(style))
        story.append(table)
    else:
        story.append(Paragraph("No data for the selected period.", sub))

    if report.note:
        story.append(Paragraph(report.note, note))

    doc.build(story, onFirstPage=_pdf_header_footer, onLaterPages=_pdf_header_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def to_excel(report: ReportData) -> bytes:
    """
    Render the report as an .xlsx workbook.

    The total row uses real SUM formulas rather than values computed in Python,
    so the sheet still recalculates correctly if someone edits or filters the
    data after downloading it.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.title[:31]  # Excel caps sheet names at 31 chars

    thin = Side(style="thin", color="DFE5F0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- Title block -------------------------------------------------------
    sheet["A1"] = report.title
    sheet["A1"].font = Font(name=XL_FONT, size=15, bold=True, color="131A28")
    sheet["A2"] = f"{report.description}, {report.date_from} to {report.date_to}"
    sheet["A2"].font = Font(name=XL_FONT, size=10, color="5B6880")
    sheet["A3"] = (f"{COMPANY} · generated "
                   f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    sheet["A3"].font = Font(name=XL_FONT, size=9, italic=True, color="5B6880")

    cursor = 5

    # --- Summary -----------------------------------------------------------
    if report.summary:
        sheet.cell(row=cursor, column=1, value="Summary").font = Font(
            name=XL_FONT, size=11, bold=True, color="2563EB")
        cursor += 1
        for label, value in report.summary:
            sheet.cell(row=cursor, column=1, value=label).font = Font(name=XL_FONT, size=10, color="5B6880")
            cell = sheet.cell(row=cursor, column=2, value=value)
            cell.font = Font(name=XL_FONT, size=10, bold=True)
            cursor += 1
        cursor += 1

    # --- Header row --------------------------------------------------------
    header_row = cursor
    for column_index, name in enumerate(report.columns, start=1):
        cell = sheet.cell(row=header_row, column=column_index, value=name)
        cell.font = Font(name=XL_FONT, size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    cursor += 1

    first_data_row = cursor
    for row in report.rows:
        for column_index, value in enumerate(row, start=1):
            cell = sheet.cell(row=cursor, column=column_index, value=value)
            cell.font = Font(name=XL_FONT, size=10)
            cell.border = border
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.number_format = "#,##0.00" if isinstance(value, float) else "#,##0"
        cursor += 1
    last_data_row = cursor - 1

    # --- Total row (formulas, not precomputed values) ----------------------
    if report.rows and report.numeric_columns:
        sheet.cell(row=cursor, column=1, value="TOTAL").font = Font(
            name=XL_FONT, size=10, bold=True)
        for index in report.numeric_columns:
            column_letter = get_column_letter(index + 1)
            cell = sheet.cell(row=cursor, column=index + 1)
            cell.value = f"=SUM({column_letter}{first_data_row}:{column_letter}{last_data_row})"
            cell.font = Font(name=XL_FONT, size=10, bold=True)
            column_values = [r[index] for r in report.rows
                             if isinstance(r[index], (int, float)) and not isinstance(r[index], bool)]
            all_integers = bool(column_values) and all(isinstance(v, int) for v in column_values)
            cell.number_format = "#,##0" if all_integers else "#,##0.00"
        for column_index in range(1, len(report.columns) + 1):
            target = sheet.cell(row=cursor, column=column_index)
            target.fill = PatternFill("solid", fgColor="E8EEF9")
            target.border = border
        cursor += 1

    if report.note:
        cursor += 1
        cell = sheet.cell(row=cursor, column=1, value=f"Note: {report.note}")
        cell.font = Font(name=XL_FONT, size=9, italic=True, color="5B6880")

    # --- Column widths, sized to content ----------------------------------
    for column_index, name in enumerate(report.columns, start=1):
        longest = len(str(name))
        for row in report.rows:
            longest = max(longest, len(str(row[column_index - 1])))
        sheet.column_dimensions[get_column_letter(column_index)].width = min(42, max(12, longest + 3))

    # Freeze the header so long tables stay readable while scrolling.
    sheet.freeze_panes = sheet.cell(row=first_data_row, column=1)

    if report.rows:
        sheet.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(report.columns))}{last_data_row}"
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


RENDERERS = {"pdf": to_pdf, "excel": to_excel}

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

EXTENSIONS = {"pdf": "pdf", "excel": "xlsx"}
