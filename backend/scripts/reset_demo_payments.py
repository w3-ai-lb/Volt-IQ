"""
Undo payments made through the portal, so the demo starts clean again.

WHY THIS EXISTS
---------------
Paying a bill from the Bills page is now a real write: it inserts a payment row
and marks the bill Paid. That is the correct behaviour, and it means a
walkthrough of the portal leaves the demo database with fewer unpaid bills than
it started with. After a few rehearsals there is nothing left to demonstrate
paying.

This removes only payments the portal created, and puts their bills back. It
leaves the seeded history alone.

HOW IT TELLS THEM APART
-----------------------
The seeder writes short references (PAY-7811). The portal writes zero-padded
six-digit ones (PAY-007972). That is a deliberate difference, not a
coincidence, and it is what makes this script safe to run against real seeded
data.

    python -m scripts.reset_demo_payments            # report only
    python -m scripts.reset_demo_payments --apply    # undo them
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime

from app.ai import alerts as alert_engine
from app.database import SessionLocal
from app.models.bill import Bill
from app.models.payment import Payment

# PAY- followed by exactly six digits: the format _next_payment_id produces.
PORTAL_PAYMENT = re.compile(r"^PAY-\d{6}$")


def main() -> int:
    apply = "--apply" in sys.argv
    session = SessionLocal()
    try:
        candidates = [
            payment
            for payment in session.query(Payment).all()
            if PORTAL_PAYMENT.match(payment.payment_id or "")
        ]

        if not candidates:
            print("No portal payments found. The demo data is already as seeded.")
            return 0

        today = datetime.now(UTC).date()
        affected: set[str] = set()

        print(f"{len(candidates)} payment(s) made through the portal:")
        for payment in candidates:
            print(f"  {payment.payment_id}  {payment.amount:>10.2f}  {payment.method}  -> {payment.bill_id}")
            if payment.bill_id:
                affected.add(payment.bill_id)

        if not apply:
            print("\nRe-run with --apply to remove them and reopen their bills.")
            return 0

        customers: set[str] = set()
        for payment in candidates:
            customers.add(payment.customer_id)
            session.delete(payment)

        for bill_id in affected:
            bill = session.get(Bill, bill_id)
            if bill is None:
                continue
            # Overdue if its due date has passed, Pending if it has not. This
            # is the same rule the seeder uses, so a reopened bill looks like
            # one that was never paid rather than one in a state of its own.
            bill.status = "Overdue" if bill.due_date < today else "Pending"

        session.commit()

        # The alert feed follows the bills, so rebuild it for anyone affected.
        for customer_id in customers:
            alert_engine.refresh_for_customer(session, customer_id)

        print(f"\nRemoved {len(candidates)} payment(s) and reopened {len(affected)} bill(s).")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
