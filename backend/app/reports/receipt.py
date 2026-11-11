"""
Payment receipts, the "Payment receipts" output of the Billing & Payment
Module (SRS Section VI-iii).

A receipt is a single-payment document, not an aggregate report, so it gets its
own portrait-A4 layout rather than reusing the landscape report renderer.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import settings
from app.core.money import money
from app.models.bill import Bill
from app.models.customer import Customer
from app.models.payment import Payment

BRAND = colors.HexColor("#2563eb")
INK = colors.HexColor("#131a28")
MUTED = colors.HexColor("#5b6880")
RULE = colors.HexColor("#dfe5f0")
BAND = colors.HexColor("#f2f6fc")
OK = colors.HexColor("#059669")

COMPANY = "NXTTRN"


def build_receipt_pdf(payment: Payment, customer: Customer, bill: Bill | None) -> bytes:
    """Render one payment as an A4 receipt PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Payment receipt {payment.payment_id}",
        author=COMPANY,
        subject="Payment receipt",
    )

    base = getSampleStyleSheet()
    brand = ParagraphStyle("brand", parent=base["Normal"], fontSize=16,
                           fontName="Helvetica-Bold", textColor=BRAND)
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, leading=24,
                        textColor=INK, spaceBefore=6, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5,
                         textColor=MUTED, spaceAfter=16)
    lbl = ParagraphStyle("lbl", parent=base["Normal"], fontSize=9, textColor=MUTED)
    val = ParagraphStyle("val", parent=base["Normal"], fontSize=10.5,
                         textColor=INK, fontName="Helvetica-Bold")
    big = ParagraphStyle("big", parent=base["Normal"], fontSize=24, leading=28,
                         textColor=OK, fontName="Helvetica-Bold")
    note = ParagraphStyle("note", parent=base["Normal"], fontSize=8, leading=11,
                          textColor=MUTED, spaceBefore=20)

    def field_rows(pairs: list[tuple[str, str]]) -> Table:
        data = [[Paragraph(label, lbl), Paragraph(value, val)] for label, value in pairs]
        table = Table(data, colWidths=[doc.width * 0.38, doc.width * 0.62])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ]))
        return table

    story: list = [
        Paragraph(COMPANY, brand),
        Paragraph("Payment Receipt", h1),
        Paragraph(f"Receipt no. {payment.payment_id} &nbsp;·&nbsp; "
                  f"Issued {datetime.now(UTC).strftime('%d %b %Y')}", sub),
    ]

    # --- Amount paid, front and centre -------------------------------------
    amount_block = Table(
        [[Paragraph("Amount paid", lbl)], [Paragraph(money(payment.amount), big)]],
        colWidths=[doc.width],
    )
    amount_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
    ]))
    story += [amount_block, Spacer(1, 18)]

    # --- Payment details ---------------------------------------------------
    story.append(Paragraph("Payment details", val))
    story.append(Spacer(1, 6))
    story.append(field_rows([
        ("Payment reference", payment.payment_id),
        ("Payment date", payment.date.strftime("%d %B %Y")),
        ("Payment method", payment.method),
        ("Status", payment.status),
    ]))
    story.append(Spacer(1, 18))

    # --- Customer ----------------------------------------------------------
    story.append(Paragraph("Customer", val))
    story.append(Spacer(1, 6))
    story.append(field_rows([
        ("Customer ID", customer.customer_id),
        ("Name", customer.name),
        ("Email", customer.email),
        ("Phone", customer.phone or "-"),
        ("Address", customer.address or "-"),
        ("Region", customer.region or "-"),
        ("Plan", customer.plan),
    ]))

    # --- Bill this payment settles -----------------------------------------
    if bill is not None:
        outstanding = float(bill.amount) - float(payment.amount)
        story.append(Spacer(1, 18))
        story.append(Paragraph("Applied to bill", val))
        story.append(Spacer(1, 6))
        story.append(field_rows([
            ("Bill reference", bill.bill_id),
            ("Billing month", bill.month),
            ("Bill amount", money(bill.amount)),
            ("Due date", bill.due_date.strftime("%d %B %Y")),
            ("Bill status", bill.status),
            ("Remaining on this bill",
             money(max(0.0, outstanding)) if outstanding > 0.005 else f"{money(0)}, settled in full"),
        ]))

    story.append(Paragraph(
        "This receipt is generated automatically by the AI-Powered Energy Analytics and "
        "Customer Engagement Platform and serves as confirmation of payment. "
        f"All amounts are in {settings.CURRENCY}.",
        note,
    ))

    doc.build(story)
    return buffer.getvalue()


def build_bill_pdf(bill: Bill, customer: Customer, payments: list[Payment]) -> bytes:
    """
    Render one bill as an A4 PDF.

    WHAT IT DOES NOT DO
    -------------------
    It does not print an energy / delivery / tax breakdown. The Bills page used
    to show one, produced by multiplying the total by 0.7, 0.2 and 0.1, which
    invented three line items that appear nowhere in the data. The Bill entity
    stores one amount, so this document states one amount, plus what has been
    paid against it. A statement that says less than a real bill is a fair
    statement; one that makes up its own line items is not.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Bill {bill.bill_id}",
        author=COMPANY,
        subject="Electricity bill",
    )

    base = getSampleStyleSheet()
    brand = ParagraphStyle("brand", parent=base["Normal"], fontSize=16,
                           fontName="Helvetica-Bold", textColor=BRAND)
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, leading=24,
                        textColor=INK, spaceBefore=6, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=9.5,
                         textColor=MUTED, spaceAfter=16)
    lbl = ParagraphStyle("lbl", parent=base["Normal"], fontSize=9, textColor=MUTED)
    val = ParagraphStyle("val", parent=base["Normal"], fontSize=10.5,
                         textColor=INK, fontName="Helvetica-Bold")
    big = ParagraphStyle("big", parent=base["Normal"], fontSize=24, leading=28,
                         textColor=INK, fontName="Helvetica-Bold")
    note = ParagraphStyle("note", parent=base["Normal"], fontSize=8, leading=11,
                          textColor=MUTED, spaceBefore=20)

    def field_rows(pairs: list[tuple[str, str]]) -> Table:
        data = [[Paragraph(label, lbl), Paragraph(str(value), val)] for label, value in pairs]
        table = Table(data, colWidths=[55 * mm, 105 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e6ebf5")),
        ]))
        return table

    paid = round(sum(float(p.amount) for p in payments), 2)
    outstanding = round(float(bill.amount) - paid, 2)

    story = [
        Paragraph(COMPANY, brand),
        Paragraph("Electricity bill", h1),
        Paragraph(f"{bill.month} &nbsp;·&nbsp; reference {bill.bill_id}", sub),
        Paragraph(money(bill.amount), big),
        Spacer(1, 18),
        Paragraph("Bill", val),
        Spacer(1, 6),
        field_rows([
            ("Bill reference", bill.bill_id),
            ("Billing month", bill.month),
            ("Amount", money(bill.amount)),
            ("Due date", bill.due_date.strftime("%d %B %Y")),
            ("Status", bill.status),
            ("Paid to date", money(paid)),
            ("Outstanding", money(max(0.0, outstanding))),
        ]),
        Spacer(1, 18),
        Paragraph("Customer", val),
        Spacer(1, 6),
        field_rows([
            ("Customer ID", customer.customer_id),
            ("Name", customer.name),
            ("Email", customer.email),
            ("Phone", customer.phone or "-"),
            ("Address", customer.address or "-"),
            ("Region", customer.region or "-"),
            ("Plan", customer.plan),
        ]),
    ]

    if payments:
        story.append(Spacer(1, 18))
        story.append(Paragraph("Payments received", val))
        story.append(Spacer(1, 6))
        story.append(field_rows([
            (p.date.strftime("%d %B %Y"), f"{money(p.amount)} · {p.method} · {p.status}")
            for p in payments
        ]))

    story.append(Paragraph(
        "This bill is generated from the readings and billing records held by the "
        "AI-Powered Energy Analytics and Customer Engagement Platform. "
        f"All amounts are in {settings.CURRENCY}.",
        note,
    ))

    doc.build(story)
    return buffer.getvalue()
