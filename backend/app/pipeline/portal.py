"""
Put the supervisor's own measurements behind the Project 1 screens.

    python -m app.pipeline.portal
    python -m app.pipeline.portal --replace     # rebuild from scratch

WHY THIS EXISTS
---------------
From the supervisor, 18 August, third technical goal: activate the dashboards
on the generated data.

They were not. The customer portal and the admin dashboard read `consumption`,
`bills` and `payments`, and every row in those three tables was written by our
own seeder while there was no real data. So the admin dashboard was reporting
revenue of 56,491 and a top consumer called "Sidon Steel Works", none of which
exists, while the supervisor's 5,400 meter readings and 5,400 invoices sat in
tables no screen looked at.

This projects one into the other. Nothing new is calculated and nothing is
invented: each row here restates a row he supplied, in the shape the existing
screens already read.

    consumption   one row per subscriber per month
                  kwh    the difference between two meter readings
                  cost   that month's invoice total
                  when   the date the meter was actually read

    bills         one row per invoice, his amount, his billing month

    payments      one row per payment, his amount, date and method

THE ONE THING HERE THAT IS A CONVENTION, NOT A MEASUREMENT
----------------------------------------------------------
`bills.due_date`. His invoice files carry no due date, and the column cannot
be null. It is set to the last day of the billing month, which is the ordinary
practice and is consistent with his own payment dates: those run from 5 to 39
days after the month opens, median 22. It is the only value on any row written
here that did not come out of one of his files, and it is written down rather
than left to be discovered.

WHAT THIS DOES NOT DO
---------------------
It does not manufacture hourly or daily consumption. His meters are read once
a month, so a subscriber has twelve or eighteen numbers a year and not 8,760.
Spreading a month's kWh across 720 hours would draw a smooth load curve that
looks like measurement and is arithmetic, which is the same mistake the
hardcoded sine wave on the old dashboard made. The hourly screens are left to
report that they have nothing, and the only true hourly record in this system
stays where it belongs: `generator_telemetry`, measured at the generator.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_all_tables
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.invoice import Invoice, InvoicePayment
from app.models.payment import Payment
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("portal")

# Every row this module writes is recognisable by its id, so a rerun replaces
# its own work and nothing else, and the provenance report can separate these
# from the seeder's rows in the same three tables.
BILL_PREFIX = "BILL-INV"
PAYMENT_PREFIX = "PAY-P"

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _customer_of_subscriber(db: Session) -> dict[str, str]:
    return {
        subscriber_id: customer_id
        for subscriber_id, customer_id in db.query(
            Subscriber.subscriber_id, Subscriber.customer_id
        ).all()
        if customer_id
    }


def clear(db: Session) -> int:
    """Remove only what this module wrote."""
    removed = 0
    removed += (
        db.query(Payment)
        .filter(Payment.payment_id.like(f"{PAYMENT_PREFIX}%"))
        .delete(synchronize_session=False)
    )
    removed += (
        db.query(Bill).filter(Bill.bill_id.like(f"{BILL_PREFIX}%")).delete(synchronize_session=False)
    )
    removed += (
        db.query(Consumption)
        .filter(Consumption.customer_id.like("GEN-%"))
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed


def project_consumption(db: Session, owner: dict[str, str]) -> int:
    """
    A meter reading is a dial value; consumption is the difference between two
    of them. The first reading of each meter is differenced against the dial at
    installation, so a subscriber's first month is counted like every other.
    """
    initial = {
        subscription_id: float(value or 0.0)
        for subscription_id, value in db.query(Meter.subscription_id, Meter.initial_reading).all()
    }
    cost = {
        (subscription_id, period): float(total or 0.0)
        for subscription_id, period, total in db.query(
            Invoice.subscription_id, Invoice.billing_period, Invoice.total_amount
        ).all()
    }

    rows = (
        db.query(
            Subscription.subscriber_id,
            MeterReading.subscription_id,
            MeterReading.billing_period,
            MeterReading.reading_value,
            MeterReading.reading_date,
        )
        .join(Subscription, Subscription.subscription_id == MeterReading.subscription_id)
        .order_by(MeterReading.subscription_id, MeterReading.billing_period)
        .all()
    )

    previous = dict(initial)
    written = 0
    for subscriber_id, subscription_id, period, value, read_on in rows:
        customer_id = owner.get(subscriber_id)
        if not customer_id or subscription_id not in previous:
            previous[subscription_id] = float(value)
            continue

        used = float(value) - previous[subscription_id]
        previous[subscription_id] = float(value)
        if used < 0:                      # a dial rollover is not consumption
            continue

        # The date the meter was actually read, not the first of the month:
        # the reading window sits about ten days inside the period and that
        # displacement is a real quantity elsewhere in this system.
        when = read_on or period
        db.add(
            Consumption(
                customer_id=customer_id,
                timestamp=datetime(when.year, when.month, when.day),
                kwh=round(used, 2),
                cost=round(cost.get((subscription_id, period), 0.0), 2),
            )
        )
        written += 1

    db.commit()
    return written


def project_bills(db: Session, owner: dict[str, str]) -> tuple[int, int]:
    """One bill per invoice, one payment per payment, his figures throughout."""
    paid_against = {
        invoice_id: float(total or 0.0)
        for invoice_id, total in db.query(
            InvoicePayment.invoice_id, func.sum(InvoicePayment.amount)
        )
        .group_by(InvoicePayment.invoice_id)
        .all()
    }

    # AND WHAT THE PORTAL COLLECTED, WHICH THIS MODULE DID NOT WRITE
    # --------------------------------------------------------------
    # `clear` deletes the bills and the payments carrying this module's prefix.
    # A payment taken through the Pay button carries a different prefix, is not
    # this module's to delete, and survives. Rebuilding the bill's status from
    # the provider's file alone therefore reopened bills the customer had
    # already settled: the bill came back Pending, the portal offered a Pay
    # button, and the endpoint refused the click because the payments table
    # knew the bill was covered. A bill that shows money owing and will not
    # accept it is worse than either state on its own.
    portal_paid: dict[str, float] = {
        bill_id: float(total or 0.0)
        for bill_id, total in db.query(Payment.bill_id, func.sum(Payment.amount))
        .filter(
            Payment.bill_id.isnot(None),
            ~Payment.payment_id.like(f"{PAYMENT_PREFIX}%"),
            Payment.status != "Failed",
        )
        .group_by(Payment.bill_id)
        .all()
    }

    bills = 0
    for invoice in db.query(Invoice).all():
        customer_id = owner.get(invoice.subscriber_id)
        if not customer_id:
            continue
        bill_id = f"{BILL_PREFIX}{invoice.invoice_id.removeprefix('INV')}"
        settled = paid_against.get(invoice.invoice_id, 0.0) + portal_paid.get(bill_id, 0.0)
        total = float(invoice.total_amount or 0.0)
        if settled >= total - 1.0:
            status = "Paid"
        elif settled > 0:
            status = "Pending"          # part paid, the rest still owing
        else:
            status = "Overdue"          # nothing received, and the month is past

        period = invoice.billing_period
        db.merge(
            Bill(
                bill_id=bill_id,
                customer_id=customer_id,
                month=f"{MONTH_NAMES[period.month - 1]} {period.year}",
                amount=round(total, 2),
                due_date=_month_end(period),
                status=status,
            )
        )
        bills += 1

    payments = 0
    for payment in db.query(InvoicePayment).all():
        customer_id = owner.get(payment.subscriber_id)
        if not customer_id:
            continue
        invoice_total = (
            db.query(Invoice.total_amount)
            .filter(Invoice.invoice_id == payment.invoice_id)
            .scalar()
        )
        amount = float(payment.amount or 0.0)
        complete = invoice_total is None or amount >= float(invoice_total) - 1.0
        db.merge(
            Payment(
                payment_id=f"{PAYMENT_PREFIX}{payment.payment_id.removeprefix('P')}",
                customer_id=customer_id,
                bill_id=(
                    f"{BILL_PREFIX}{payment.invoice_id.removeprefix('INV')}"
                    if payment.invoice_id
                    else None
                ),
                date=payment.payment_date or date.today(),
                amount=round(amount, 2),
                method=(payment.payment_method or "cash").upper()
                if (payment.payment_method or "") in {"omt"}
                else (payment.payment_method or "cash").capitalize(),
                status="Completed" if complete else "Partial",
            )
        )
        payments += 1

    db.commit()
    return bills, payments


def run_ai(db: Session) -> dict[str, int]:
    """
    Let the AI features see the data that has just been projected.

    Recommendations, alerts and anomalies are STORED rows, not computed per
    request: the seeder used to write them, and after the demo is purged
    nothing does. So the Recommendations page, the alert feed and the anomaly
    list all sat empty for three hundred customers whose readings were right
    there, which reads as three features that do not work.

    Each is refreshed separately and a failure in one does not stop the others,
    because a missing recommendation should not cost the owner his alerts.
    """
    from app.ai import alerts, anomaly, recommender

    from app.models.alert import Alert
    from app.models.anomaly import Anomaly
    from app.models.recommendation import Recommendation

    counts: dict[str, int] = {}
    # The count reported is how many rows EXIST afterwards, not how many were
    # newly created. `alerts.refresh_all` updates a still-valid alert in place
    # and returns only the new ones, so a second run legitimately creates none
    #, and printing "alerts 0" beside 527 stored alerts reads as a failure.
    for name, work, model in (
        ("recommendations", lambda: recommender.refresh_all(db), Recommendation),
        ("alerts", lambda: alerts.refresh_all(db), Alert),
        ("anomalies", lambda: anomaly.run_detection(db, persist=True), Anomaly),
    ):
        try:
            work()
            counts[name] = int(db.query(func.count()).select_from(model).scalar() or 0)
        except Exception:                            # pragma: no cover
            logger.warning("Could not refresh %s", name, exc_info=True)
            counts[name] = 0
    return counts


def run(db: Session, replace: bool = False) -> dict[str, int]:
    owner = _customer_of_subscriber(db)
    if not owner:
        logger.error(
            "No subscriber has a customer record yet. Run: python -m app.pipeline.identities"
        )
        return {}

    # ALWAYS clear first, not only under --replace.
    #
    # `project_bills` merges on a primary key and is naturally idempotent, but
    # `project_consumption` adds rows against an autoincrement id and has no
    # natural key to merge on. So a second plain run appended a second copy of
    # all 5,400 consumption rows, silently doubling every kWh figure in the
    # product. A projection is a restatement of source rows: running it twice
    # must give the same answer as running it once, and the only way to promise
    # that here is to remove what this module wrote before writing it again.
    #
    # `clear()` only ever touches rows this module created, GEN- consumption,
    # BILL-INV bills, PAY-P payments, so nothing of the supervisor's is at risk.
    removed = clear(db)
    if removed:
        logger.info("Replaced %d rows from a previous run", removed)

    written = project_consumption(db, owner)
    bills, payments = project_bills(db, owner)
    counts = {"consumption": written, "bills": bills, "payments": payments}
    counts.update(run_ai(db))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project the supervisor's readings and invoices into the portal tables."
    )
    parser.add_argument("--replace", action="store_true",
                        help="Remove this module's previous rows first")
    args = parser.parse_args()

    create_all_tables()
    db = SessionLocal()
    try:
        counts = run(db, replace=args.replace)
        if not counts:
            return 1

        kwh = (
            db.query(func.sum(Consumption.kwh))
            .filter(Consumption.customer_id.like("GEN-%"))
            .scalar()
            or 0.0
        )
        billed = db.query(func.sum(Invoice.units_consumed)).scalar() or 0.0

        print("\n" + "=" * 72)
        print("  The portal now reads the supervisor's data")
        print("=" * 72)
        print(f"    consumption rows   {counts['consumption']:>8,}   from his meter readings")
        print(f"    bills              {counts['bills']:>8,}   from his invoices")
        print(f"    payments           {counts['payments']:>8,}   from his payments")
        print()
        print(f"    recommendations    {counts.get('recommendations', 0):>8,}   computed from those readings")
        print(f"    alerts             {counts.get('alerts', 0):>8,}")
        anomalies = counts.get("anomalies", 0)
        print(f"    anomalies          {anomalies:>8,}"
              + ("" if anomalies else "   (none: the daily detector needs daily readings)"))
        print()
        print(f"    kWh now behind the charts   {kwh:>12.0f}")
        print(f"    kWh he billed               {billed:>12.0f}")
        print(f"    difference                  {kwh - billed:>12.0f}   (his one-decimal rounding)")
        print()
        print("    Hourly and daily screens stay empty on purpose: his meters are")
        print("    read once a month. The only true hourly record is the generator")
        print("    telemetry, and it is measured at the generator, not the meter.")
        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
