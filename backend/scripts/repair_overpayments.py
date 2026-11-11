"""
Repair the bills that were charged twice, and prove there are no others.

WHAT HAPPENED
-------------
Pressing Pay used to default to the bill's face value rather than to what was
still owed on it. 845 of this provider's 5,400 invoices are part paid, so on
any one of those the button recorded the whole bill a second time. The
endpoint has been fixed (`app/routers/billing.py`, "WHAT IS ACTUALLY STILL
OWED ON THIS BILL"), but a fix in the code does not unwrite the row it already
wrote, and `owed.py` clamps a negative balance to zero, so the customer's
screen looked right while the provider's revenue carried money nobody paid.

WHAT THIS DOES
--------------
For every bill where the payments recorded against it exceed its face value,
the portal payment is reduced to what was actually still owed at the moment it
was taken: the bill total minus everything the provider's own file already
records against it. Nothing is invented; the corrected figure is arithmetic on
the provider's numbers.

Only payments this platform wrote are touched. A payment loaded from the
provider's records is his, is evidence, and is never edited here: if one of
those ever exceeds a bill, the script says so and changes nothing, because
that is a discrepancy for the provider to explain rather than for us to erase.

    python -m scripts.repair_overpayments --dry-run
    python -m scripts.repair_overpayments
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func                                        # noqa: E402

from app.core.money import money                                   # noqa: E402
from app.database import SessionLocal                              # noqa: E402
from app.models.bill import Bill                                   # noqa: E402
from app.models.payment import Payment                             # noqa: E402

# Payments written by the loader carry this prefix; the portal's do not.
PIPELINE_PREFIX = "PAY-P"

# A bill is over-collected only if it is over by real money, not by rounding.
TOLERANCE = 1.0


def find(db):
    """Every bill holding more money than it asked for."""
    received = (
        db.query(
            Payment.bill_id.label("bill_id"),
            func.sum(Payment.amount).label("total"),
        )
        .filter(Payment.bill_id.isnot(None), Payment.status != "Failed")
        .group_by(Payment.bill_id)
        .subquery()
    )
    return (
        db.query(Bill, received.c.total)
        .join(received, received.c.bill_id == Bill.bill_id)
        .filter(received.c.total > Bill.amount + TOLERANCE)
        .order_by(Bill.bill_id)
        .all()
    )


def repair(dry_run: bool) -> int:
    db = SessionLocal()
    try:
        rows = find(db)
        if not rows:
            print("No bill holds more than it asked for. Nothing to repair.")
            return 0

        repaired = untouched = 0
        for bill, total in rows:
            over = float(total) - float(bill.amount)
            print(f"\n{bill.bill_id}  {bill.month}  {bill.customer_id}")
            print(f"  bill      {money(bill.amount)}")
            print(f"  received  {money(total)}   over by {money(over)}")

            payments = (
                db.query(Payment)
                .filter(Payment.bill_id == bill.bill_id, Payment.status != "Failed")
                .order_by(Payment.date)
                .all()
            )
            ours = [p for p in payments if not p.payment_id.startswith(PIPELINE_PREFIX)]
            if not ours:
                print("  every payment on this bill came from the provider's own "
                      "records. Left alone: this is his to explain, not ours to edit.")
                untouched += 1
                continue

            # What the provider's file already recorded, and therefore what was
            # genuinely still owed when the portal took its payment.
            theirs = sum(float(p.amount) for p in payments if p not in ours)
            owed_then = round(max(0.0, float(bill.amount) - theirs), 2)
            mine = ours[-1]                       # the one that took it over

            print(f"  provider had recorded {money(theirs)}, so {money(owed_then)} "
                  f"was owed when {mine.payment_id} was taken")
            print(f"  {mine.payment_id}: {money(mine.amount)} -> {money(owed_then)}")

            if not dry_run:
                mine.amount = owed_then
                mine.status = "Completed" if owed_then + theirs >= float(bill.amount) - TOLERANCE \
                    else "Partial"
            repaired += 1

        if dry_run:
            print(f"\nDry run. {repaired} payment(s) would be corrected, "
                  f"{untouched} left alone.")
            db.rollback()
        else:
            db.commit()
            print(f"\n{repaired} payment(s) corrected, {untouched} left alone.")
            remaining = find(db)
            print("Re-checked:", "clean" if not remaining
                  else f"{len(remaining)} still over-collected")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would change and write nothing")
    raise SystemExit(repair(parser.parse_args().dry_run))
