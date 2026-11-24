"""
One bill, seen everywhere (Stage 2, "Linked billing").

THE PROBLEM THIS SOLVES
-----------------------
The platform grew two billing ledgers from two internship projects:

    portal side    bills + payments                   (customer -> bill)
    CRM side       invoices + invoice_payments        (subscriber -> invoice)

A field employee's reading created an invoice that the office could see but
the customer could not: their Bills page reads `bills`. And a payment made in
the portal never reached the CRM.

HOW IT IS SOLVED
----------------
The CRM invoice is the record of truth for anything metered. Every time one
is issued for a subscriber who has a customer account, a matching portal bill
is written in the same transaction, linked by `bills.invoice_id`. Payments are
mirrored both ways and linked by `payments.invoice_payment_id`:

    CRM payment   (POST /crm/payments)        -> also a portal payment
    portal payment (POST /bills/{id}/pay)      -> also an invoice payment

So every existing screen, report and AI model keeps reading the table it was
built on, and they all agree. Merging the two ledgers into one table is a
later step (see docs/ARCHITECTURE.md, roadmap).
"""

from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoicePayment
from app.models.payment import Payment
from app.models.subscription import Subscriber

logger = logging.getLogger(__name__)

DUE_AFTER_DAYS = 15
PORTAL_COLLECTOR = "PORTAL"


def month_label(period: date) -> str:
    """The portal's month format, e.g. "Jun 2026"."""
    return f"{calendar.month_abbr[period.month]} {period.year}"


def _customer_of(db: Session, subscriber_id: str) -> Customer | None:
    sub = db.get(Subscriber, subscriber_id)
    if sub is None or not sub.customer_id:
        return None
    customer = db.get(Customer, sub.customer_id)
    return customer if customer is not None and customer.role == "customer" else None


def bill_for_invoice(db: Session, invoice_id: str) -> Bill | None:
    return db.query(Bill).filter(Bill.invoice_id == invoice_id).first()


def link_invoice(db: Session, invoice: Invoice, issued_on: date | None = None) -> Bill | None:
    """
    Write (or update) the portal bill for a CRM invoice. Call before commit.
    Returns None when the subscriber has no customer account to show it to.
    """
    customer = _customer_of(db, invoice.subscriber_id)
    if customer is None:
        return None
    bill = bill_for_invoice(db, invoice.invoice_id)
    issued_on = issued_on or invoice.billing_period
    if bill is None:
        bill = Bill(
            bill_id=f"BILL-{invoice.invoice_id}"[:30],
            customer_id=customer.customer_id,
            month=month_label(invoice.billing_period),
            amount=round(float(invoice.total_amount or 0.0), 2),
            due_date=issued_on + timedelta(days=DUE_AFTER_DAYS),
            status="Pending",
            invoice_id=invoice.invoice_id,
        )
        db.add(bill)
    else:
        bill.amount = round(float(invoice.total_amount or 0.0), 2)
    db.flush()
    return bill


def _settle_bill_status(db: Session, bill: Bill) -> None:
    received = (
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(Payment.bill_id == bill.bill_id).scalar()
        or 0.0
    )
    if received >= float(bill.amount) - 0.005:
        bill.status = "Paid"


def mirror_crm_payment(db: Session, ip: InvoicePayment) -> Payment | None:
    """A payment taken in the CRM or on the phone also appears in the customer's portal."""
    if not ip.invoice_id:
        return None
    bill = bill_for_invoice(db, ip.invoice_id)
    if bill is None:
        return None
    existing = db.query(Payment).filter(Payment.invoice_payment_id == ip.payment_id).first()
    if existing is not None:
        return existing
    received = (
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(Payment.bill_id == bill.bill_id).scalar()
        or 0.0
    )
    payment = Payment(
        payment_id=f"P-{ip.payment_id}"[:30],
        customer_id=bill.customer_id,
        bill_id=bill.bill_id,
        date=ip.payment_date or date.today(),
        amount=round(float(ip.amount or 0.0), 2),
        method=(ip.payment_method or "Office").strip() or "Office",
        status="Completed" if received + float(ip.amount or 0.0) >= float(bill.amount) - 0.005 else "Partial",
        invoice_payment_id=ip.payment_id,
    )
    db.add(payment)
    db.flush()
    _settle_bill_status(db, bill)
    return payment


def mirror_portal_payment(db: Session, payment: Payment, bill: Bill) -> InvoicePayment | None:
    """A payment made in the customer portal also settles the CRM invoice."""
    if not bill.invoice_id:
        return None
    invoice = db.get(Invoice, bill.invoice_id)
    if invoice is None:
        return None
    ip = InvoicePayment(
        payment_id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        invoice_id=invoice.invoice_id,
        subscriber_id=invoice.subscriber_id,
        amount=payment.amount,
        currency=invoice.currency,
        payment_method=payment.method,
        payment_date=payment.date,
        collected_by=PORTAL_COLLECTOR,
        receipt_no=f"RCP-{payment.payment_id}"[:30],
        notes="Paid in the customer portal",
    )
    db.add(ip)
    db.flush()
    payment.invoice_payment_id = ip.payment_id
    return ip


def refresh_customer_feeds(db: Session, invoice_or_bill_customer_id: str | None) -> None:
    """New or settled bills change the customer's alerts; refresh them, never fail the caller."""
    if not invoice_or_bill_customer_id:
        return
    try:
        from app.ai import alerts as alert_engine

        alert_engine.refresh_for_customer(db, invoice_or_bill_customer_id)
    except Exception:  # pragma: no cover - the bill is saved either way
        logger.exception("Alert refresh failed for %s", invoice_or_bill_customer_id)
        db.rollback()
