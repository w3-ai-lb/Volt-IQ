"""
AI Module, Payment-Default Risk Scoring.

The Proposal problem statement names this directly: *"No early warning system
exists for customers at risk of payment default or unusual usage."* Unusual
usage is covered by anomaly detection; this is the other half. SRS Section
VI-vii also lists "Risk notifications" as an output of the Reporting Module.

Scored rather than classified, because there is no labelled default history to
train a classifier on, a utility only learns who defaulted after it happened,
and this dataset has no such labels. A transparent weighted score built from
four measurable signals is defensible in a review, explains itself to the
member of staff who has to act on it, and does not pretend to a confidence it
has not earned.

The four signals, weighted out of 100:

  overdue exposure   (35)  how much is currently unpaid, relative to the
                           customer's own typical bill, three million pounds
                           outstanding means something different to a household
                           than to a factory
  payment latency    (25)  average days between a bill falling due and being
                           paid, across the customer's history
  overdue history    (25)  the share of that customer's bills that have ever
                           gone overdue
  recency            (15)  how long since the last payment of any kind, counted
                           to the date the data reaches, not to today

A customer with no billing history at all scores 0 and is reported as
"unknown" rather than "safe": absence of evidence is not evidence of low risk,
and a new account should not be presented as a proven payer.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.analytics import asof, owed
from app.core.money import money
from app.models.bill import Bill
from app.models.customer import Customer
from app.models.payment import Payment

logger = logging.getLogger(__name__)

WEIGHT_EXPOSURE = 35.0
WEIGHT_LATENCY = 25.0
WEIGHT_HISTORY = 25.0
WEIGHT_RECENCY = 15.0

# Latency at or above this counts as fully late for scoring purposes.
LATENCY_CAP_DAYS = 45.0
# Billing is monthly, so a gap of about one cycle plus slack is simply where
# the customer is in that cycle, not a warning sign. Recency risk starts
# accruing only beyond this, otherwise every account carries a few points of
# noise for having paid three weeks ago like everybody else.
RECENCY_GRACE_DAYS = 45.0
# No payment for this long is treated as maximum recency risk.
RECENCY_CAP_DAYS = 150.0
# Outstanding at this multiple of a typical bill is maximum exposure risk.
EXPOSURE_CAP_RATIO = 3.0

BAND_HIGH = 65.0
BAND_MEDIUM = 35.0

# WHAT THE BANDS LOOK LIKE ON THIS PROVIDER'S DATA, AND WHY THEY ARE NOT TUNED
# ---------------------------------------------------------------------------
# Scored as of the export's newest reading (12 June 2026), on a database loaded
# from data/ishtirak by load-data.bat: 269 Low, 31 Medium, 0 High. The 24
# accounts with a bill against which nothing has been received all score 35 or
# more on their own. The High band is empty because no account reaches 65 out
# of 100: the latency signal is worth 25 points and contributes nothing to
# anybody, since his subscribers pay inside the billing month (see Signal 2).
# The highest score in the portfolio is 63.6.
#
# The thresholds are deliberately left where they are rather than lowered until
# the band fills up. Moving them would not find one additional customer at risk;
# it would relabel customers already visible at the top of the same ranked list,
# which is what staff actually work through. If real due dates arrive with the
# billing system, or payments start arriving late, the signal becomes live and
# these cut-points mean what they say without anybody having to remember that
# they were bent once.
#
# The ranking is the product. The band is a label on it.


def _band(score: float, has_unanswered_bill: bool = False) -> str:
    """
    The band an account belongs in.

    WHAT `has_unanswered_bill` MEANS, AND WHY IT IS NOT "HAS AN OVERDUE BILL"
    ------------------------------------------------------------------------
    The promotion used to fire for any bill past its due date. Against this
    provider's data that put 281 of 300 accounts into Medium, "worth a
    reminder", which is not a triage list, it is the customer list with a
    colour on it. Three facts combined to produce it:

      * 292 of his 300 subscribers carry a balance of some kind. Arrears are
        normal in this business, not a warning sign.
      * the due date is not his. His invoices carry none, so the pipeline sets
        it to the last day of the billing month, and that convention is then
        being used to overrule his own record of what has been paid.
      * the export ends in June 2026, so every unpaid bill in it is past its
        due date by definition, whatever happened.

    A bill against which NOTHING has ever been received is a different fact,
    and it is his: 24 accounts have one. That is a list somebody can work
    through in an afternoon, which is what the panel is for.
    """
    if score >= BAND_HIGH:
        return "High"
    if score >= BAND_MEDIUM:
        return "Medium"
    return "Medium" if has_unanswered_bill else "Low"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def reference_date(db: Session) -> date:
    """
    The day the recency signal counts to: the date the data reaches.

    WHY NOT TODAY
    -------------
    It used to be the wall clock, so the same data scored higher every day that
    passed without new data. On the provider's export, which ends in June 2026,
    the portfolio went from 1 High and 30 Medium as of 10 July to 5 High and 58
    Medium on 13 October and 8 High and 91 Medium by the end of the year, with
    no payment, bill or reading changed: the "early warning" was a calendar.

    This is the anchor the dashboards use (app/analytics/asof.py): the newest
    meter reading, capped at today. With live data that is today. Payments do
    not move it, for the reason given there: one customer paying through the
    portal today would otherwise redefine "now" for every other account.
    """
    return asof.anchor(db).as_of


def score_customer(db: Session, customer: Customer, today: date | None = None) -> dict:
    """
    Score one customer. Returns a dict ready for the API layer.

    `today` is the reference date (see `reference_date`); score_all computes it
    once for the whole portfolio.
    """
    today = today or reference_date(db)

    bills = db.query(Bill).filter(Bill.customer_id == customer.customer_id).all()
    payments = (
        db.query(Payment)
        .filter(Payment.customer_id == customer.customer_id)
        .order_by(Payment.date.desc())
        .all()
    )

    if not bills:
        return {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "region": customer.region,
            "plan": customer.plan,
            "score": 0.0,
            "band": "Unknown",
            "outstanding": 0.0,
            "overdue_bills": 0,
            "avg_days_late": 0.0,
            "days_since_payment": None,
            "reasons": ["No billing history yet, not enough evidence to score."],
        }

    typical_bill = sum(b.amount for b in bills) / len(bills)
    # Two different things, kept apart because they were previously one.
    #   unpaid       still carries a balance; some money may have arrived
    #   unanswered   nothing whatever has been received against it
    # "Past the due date" is not used: the due date is OUR convention, not his
    # (see _band), and every unpaid bill in an export that has ended is past it.
    unpaid = [b for b in bills if b.status != "Paid"]
    unanswered = [b for b in bills if b.status == "Overdue"]
    # Net of what has already been paid against each bill. Summing the face
    # value of part-paid invoices inflated both this score's exposure signal
    # and the "amount at risk" on the admin panel: 9.87 billion pounds against
    # a true 4.17. See app/analytics/owed.py.
    outstanding = owed.outstanding_for(db, customer.customer_id)

    reasons: list[str] = []

    # --- Signal 1: outstanding exposure relative to a typical bill --------
    exposure_ratio = outstanding / typical_bill if typical_bill > 0 else 0.0
    exposure = _clamp01(exposure_ratio / EXPOSURE_CAP_RATIO)
    if exposure_ratio >= 1.0:
        reasons.append(
            f"{money(outstanding)} outstanding, {exposure_ratio:.1f}x a typical bill"
        )

    # --- Signal 2: how late this customer pays, historically --------------
    # Matched by bill, so a customer who always pays two weeks late scores
    # worse than one who pays on the day, even though both end up settled.
    #
    # A FINDING ABOUT THIS PROVIDER, NOT A DEAD SIGNAL: measured against the
    # month-end due date, 73% of his 4,384 settled invoices were paid BEFORE it
    # and the latest any payment ever arrived was 12 days after. The mean lag
    # is therefore negative for almost every subscriber and this signal
    # contributes nothing to almost every score. That is what his data says, 
    # his customers pay inside the month, and it is left visible rather than
    # rescaled to manufacture a spread the evidence does not support.
    settled = [b for b in bills if b.status == "Paid"]
    by_bill: dict[str, date] = {}
    for payment in payments:
        if payment.bill_id and payment.bill_id not in by_bill:
            by_bill[payment.bill_id] = payment.date

    lags = [
        (by_bill[b.bill_id] - b.due_date).days
        for b in settled
        if b.bill_id in by_bill
    ]
    avg_days_late = max(0.0, sum(lags) / len(lags)) if lags else 0.0
    latency = _clamp01(avg_days_late / LATENCY_CAP_DAYS)
    if avg_days_late >= 7:
        reasons.append(f"Pays {avg_days_late:.0f} days late on average")

    # --- Signal 3: share of this customer's bills still unsettled ---------
    # Counted once. It used to add the unanswered bills to the past-due ones,
    # and every unanswered bill is also past due, so a customer with fourteen
    # of eighteen unpaid scored 28/18 and saturated the signal at its cap.
    history = _clamp01(len(unpaid) / len(bills))
    if unanswered:
        reasons.append(
            f"{len(unanswered)} bills with nothing paid against them"
            if len(unanswered) > 1 else "1 bill with nothing paid against it"
        )
    if len(unpaid) > len(unanswered):
        part = len(unpaid) - len(unanswered)
        reasons.append(
            f"{part} part-paid bill{'s' if part > 1 else ''} still carrying a balance"
        )

    # --- Signal 4: how long since any payment -----------------------------
    days_since_payment: int | None = None
    if payments:
        # Never negative: a payment dated after the reference date (the
        # provider's export runs a few days past its last reading, and a portal
        # payment is dated the day it is made) means the account paid recently.
        days_since_payment = max(0, (today - payments[0].date).days)
        overdue_by = days_since_payment - RECENCY_GRACE_DAYS
        recency = _clamp01(overdue_by / (RECENCY_CAP_DAYS - RECENCY_GRACE_DAYS))
        if days_since_payment >= 60:
            reasons.append(f"No payment received for {days_since_payment} days")
    else:
        recency = 1.0
        reasons.append("No payment has ever been received")

    score = (
        exposure * WEIGHT_EXPOSURE
        + latency * WEIGHT_LATENCY
        + history * WEIGHT_HISTORY
        + recency * WEIGHT_RECENCY
    )

    # A suspended account is already a realised problem, not a predicted one,
    # but it should not drop out of the list staff work through.
    if customer.status == "Suspended":
        score = min(100.0, score + 10.0)
        reasons.append("Account is currently suspended")

    if not reasons:
        reasons.append("Pays on time with nothing outstanding")

    return {
        "customer_id": customer.customer_id,
        "name": customer.name,
        "region": customer.region,
        "plan": customer.plan,
        "score": round(score, 1),
        "band": _band(score, has_unanswered_bill=bool(unanswered)),
        "outstanding": round(outstanding, 2),
        # Bills against which nothing at all has arrived. "Past the due date"
        # is not reported: with the export ending in June it is true of every
        # unpaid bill, so the column would read "all of them" for 292 of 300.
        "overdue_bills": len(unanswered),
        "avg_days_late": round(avg_days_late, 1),
        "days_since_payment": days_since_payment,
        "reasons": reasons,
    }


def score_all(db: Session, limit: int | None = None, today: date | None = None) -> list[dict]:
    """Score every customer account, riskiest first, all against one reference date."""
    today = today or reference_date(db)
    customers = (
        db.query(Customer)
        .filter(Customer.role == "customer")
        .all()
    )
    scored = [score_customer(db, customer, today=today) for customer in customers]
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored[:limit] if limit else scored


def portfolio_summary(db: Session) -> dict:
    """Counts per risk band plus the total money exposed, for the admin KPI row."""
    today = reference_date(db)
    scored = score_all(db, today=today)
    bands = {"High": 0, "Medium": 0, "Low": 0, "Unknown": 0}
    for row in scored:
        bands[row["band"]] = bands.get(row["band"], 0) + 1

    at_risk = [r for r in scored if r["band"] in ("High", "Medium")]
    return {
        "high": bands["High"],
        "medium": bands["Medium"],
        "low": bands["Low"],
        "unknown": bands["Unknown"],
        "amount_at_risk": round(sum(r["outstanding"] for r in at_risk), 2),
        # The date the recency signal counted to, so the page can say so.
        "as_of": today,
        "customers": scored,
    }
