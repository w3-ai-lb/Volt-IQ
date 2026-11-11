"""
What a customer still owes, counted once and the same way everywhere.

THE PROBLEM THIS SOLVES
-----------------------
Four places computed an outstanding balance and two of them got a different
answer for the same account on the same afternoon:

    the customer dashboard   7,962,610 LBP
    the assistant            3,926,058 LBP

Both from the same two bills. The dashboard summed the FACE VALUE of every
bill not marked Paid; the assistant read `customers.balance`, which the
identity pipeline computes as invoiced minus received.

The difference is part payments. 845 of this provider's 5,400 invoices carry
status "Pending", which app/pipeline/portal.py assigns to a bill where SOME
money arrived and some is still owing. Summing the face value of those bills
charges the customer again for what he has already paid. On the account above
it more than doubled the figure, and the same arithmetic sat behind the admin
Revenue page's outstanding total and the "amount at risk" on the payment-risk
panel.

Money owed is one quantity. It is defined here, and everything that reports it
calls this.

WHY NOT JUST READ `customers.balance`
-------------------------------------
Because that column is a stored snapshot, written when identities are
generated. It is right until the next payment is recorded and then it is
stale, whereas these queries are answered from the bills and payments
themselves. Nothing reads that column any more except as a fallback for a
customer who has no bills at all: `outstanding_for_all` answers the whole
customer list in one grouped query, so there was never a reason to keep it.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.payment import Payment


def _paid_against_bills(db: Session, customer_id: str | None = None):
    """Sub-query: total received per bill_id."""
    query = db.query(
        Payment.bill_id.label("bill_id"),
        func.coalesce(func.sum(Payment.amount), 0.0).label("received"),
    ).filter(Payment.bill_id.isnot(None))
    if customer_id is not None:
        query = query.filter(Payment.customer_id == customer_id)
    return query.group_by(Payment.bill_id).subquery()


def outstanding_for(db: Session, customer_id: str) -> float:
    """
    What this customer still owes: unpaid bills, less what has been paid
    against each of them. Never negative, an overpayment is a credit, not a
    debt, and reporting it as a negative balance on a card reads as an error.
    """
    paid = _paid_against_bills(db, customer_id)
    total = (
        db.query(
            func.coalesce(
                func.sum(Bill.amount - func.coalesce(paid.c.received, 0.0)), 0.0
            )
        )
        .outerjoin(paid, paid.c.bill_id == Bill.bill_id)
        .filter(Bill.customer_id == customer_id, Bill.status != "Paid")
        .scalar()
    )
    return max(0.0, round(float(total or 0.0), 2))


def outstanding_total(db: Session) -> float:
    """The same figure across every account, for the admin revenue page."""
    paid = _paid_against_bills(db)
    total = (
        db.query(
            func.coalesce(
                func.sum(
                    func.max(Bill.amount - func.coalesce(paid.c.received, 0.0), 0.0)
                ),
                0.0,
            )
        )
        .outerjoin(paid, paid.c.bill_id == Bill.bill_id)
        .filter(Bill.status != "Paid")
        .scalar()
    )
    return round(float(total or 0.0), 2)


def outstanding_for_all(db: Session) -> dict[str, float]:
    """
    What every customer still owes, in one query.

    The admin's customer list used to print `customers.balance`, the snapshot
    column the identity pipeline writes once. A customer could settle a bill
    from the portal and the admin's own screen would keep showing the old
    balance for ever, while the risk panel and the revenue page beside it moved.
    A stale figure on the main customer screen is the same defect as a wrong
    one; it just takes longer to notice.

    Per-row queries were the reason it was left alone. There is no need: one
    grouped query answers it for all three hundred.
    """
    paid = _paid_against_bills(db)
    rows = (
        db.query(
            Bill.customer_id,
            func.sum(Bill.amount - func.coalesce(paid.c.received, 0.0)),
        )
        .outerjoin(paid, paid.c.bill_id == Bill.bill_id)
        .filter(Bill.status != "Paid")
        .group_by(Bill.customer_id)
        .all()
    )
    return {cid: max(0.0, round(float(total or 0.0), 2)) for cid, total in rows}


def outstanding_between(db: Session, date_from, date_to) -> float:
    """Still owed on bills that fell due inside a window. Used by the reports."""
    paid = _paid_against_bills(db)
    total = (
        db.query(
            func.coalesce(
                func.sum(
                    func.max(Bill.amount - func.coalesce(paid.c.received, 0.0), 0.0)
                ),
                0.0,
            )
        )
        .outerjoin(paid, paid.c.bill_id == Bill.bill_id)
        .filter(
            Bill.status != "Paid",
            Bill.due_date >= date_from,
            Bill.due_date <= date_to,
        )
        .scalar()
    )
    return round(float(total or 0.0), 2)


def owed_on(bill: Bill, received: float) -> float:
    """What is left on one bill. Kept here so the rule lives in one file."""
    return max(0.0, float(bill.amount or 0.0) - float(received or 0.0))
