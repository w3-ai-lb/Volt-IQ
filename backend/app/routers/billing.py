"""Bills, payments, recommendations, alerts and profile endpoints."""

from datetime import UTC, datetime

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import alerts as alert_engine
from app.ai import recommender
from app.core.deps import get_current_user
from app.core.i18n import localize, request_language
from app.database import get_db
from app.models.alert import Alert
from app.models.bill import Bill
from app.models.customer import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Customer
from app.core.money import money
from app.models.payment import Payment
from app.models.recommendation import Recommendation
from app.schemas.common import CamelModel
from app.schemas.billing import (
    AlertOut,
    AlertUpdate,
    AlertUpdateOut,
    BillOut,
    PaymentOut,
    ProfileOut,
    ProfileUpdate,
    RecommendationOut,
    RecommendationUpdate,
    RecommendationUpdateOut,
)

router = APIRouter(tags=["Billing & Engagement"])


# ---------------------------------------------------------------------------
# Serialisation helpers: map ORM rows onto the shapes the frontend expects
# ---------------------------------------------------------------------------
# A failed payment is not money. Counting one as received shrinks what a bill
# still owes and can settle it on paper without a pound arriving, so every
# place that sums payments against a bill excludes them.
RECEIVED = Payment.status != "Failed"


def paid_against(db: Session, bill_ids: list[str]) -> dict[str, float]:
    """How much has actually been received against each of these bills."""
    if not bill_ids:
        return {}
    rows = (
        db.query(Payment.bill_id, func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(Payment.bill_id.in_(bill_ids), RECEIVED)
        .group_by(Payment.bill_id)
        .all()
    )
    return {bill_id: float(total or 0.0) for bill_id, total in rows}


def serialize_bill(bill: Bill, received: float = 0.0) -> dict:
    amount = round(float(bill.amount), 2)
    return {
        "id": bill.bill_id,
        "month": bill.month,
        "amount": amount,
        "due_date": bill.due_date,
        "status": bill.status,
        "paid": round(received, 2),
        "remaining": round(max(0.0, amount - received), 2),
    }


def serialize_payment(payment: Payment) -> dict:
    return {
        "id": payment.payment_id,
        "date": payment.date,
        "amount": round(float(payment.amount), 2),
        "method": payment.method,
        "status": payment.status,
        "bill_id": payment.bill_id,
    }


def serialize_recommendation(rec: Recommendation, lang: str = "en") -> dict:
    """The stored English, written in the reader's language (app/core/i18n.py)."""
    return {
        "id": f"rec-{rec.recommendation_id}",
        "title": localize(rec.title, lang),
        "description": localize(rec.description, lang),
        "estimated_savings": round(float(rec.estimated_savings), 2),
        "priority": rec.priority,
        "icon": rec.icon,
        "completed": bool(rec.completed),
    }


def serialize_alert(alert: Alert, lang: str = "en") -> dict:
    """The stored English, written in the reader's language (app/core/i18n.py)."""
    return {
        "id": f"a-{alert.alert_id}",
        "type": alert.type,
        "title": localize(alert.title, lang),
        "message": localize(alert.message, lang),
        "severity": alert.severity,
        "date": alert.date,
        "read": bool(alert.read),
    }


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------
@router.get("/bills", response_model=list[BillOut])
def get_bills(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    bills = (
        db.query(Bill)
        .filter(Bill.customer_id == current_user.customer_id)
        .order_by(Bill.due_date)
        .all()
    )
    received = paid_against(db, [bill.bill_id for bill in bills])
    return [serialize_bill(bill, received.get(bill.bill_id, 0.0)) for bill in bills]


@router.get("/bills/{bill_id}", response_model=BillOut)
def get_bill(
    bill_id: str,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    bill = db.get(Bill, bill_id)

    # Ownership check: a customer may only read their own bills.
    if bill is None or (
        bill.customer_id != current_user.customer_id and current_user.role != "admin"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")

    return serialize_bill(bill, paid_against(db, [bill.bill_id]).get(bill.bill_id, 0.0))


# The channels this provider actually collects through, taken from his own
# payment records: 4,432 Cash, 527 OMT, 270 Whish, and nothing else. There is
# no card processing in this business and none is integrated here.
PAYMENT_METHODS = ("Cash", "OMT", "Whish")


class BillPaymentRequest(CamelModel):
    """
    How the customer says they paid.

    `amount` is optional: the common case is paying the whole bill, and making
    the caller repeat a figure the server already knows is how partial payments
    get recorded by accident.

    `method` defaulted to "Online Card", which is not one of the three channels
    the provider uses and not something this platform can do: the endpoint
    records a book entry, no money moves, and every real payment in his files
    arrived as cash or through OMT or Whish. A default nobody can honour writes
    a false record of how the money came in.
    """

    method: Literal["Cash", "OMT", "Whish"] = "Cash"
    amount: float | None = None


def _next_payment_id(db: Session) -> str:
    """
    Next payment reference, following the PAY-000123 format.

    WHY THIS READS EVERY ID INSTEAD OF ASKING THE DATABASE FOR THE LAST ONE
    -----------------------------------------------------------------------
    It used to take the single highest id by string order and parse the digits
    after the dash. Two id shapes live in this table: PAY-000123 from this
    endpoint, and PAY-P0004953 from app/pipeline/portal.py, which carries the
    provider's own payment reference. Sorted as text, PAY-P0005228 comes after
    every numeric one, so the query always returned a P id, int("P0005228")
    raised, the except branch set the counter back to zero, and every payment
    this endpoint issued was called PAY-000001.

    The first one worked. The second collided with the primary key and the
    customer got a 500 with no explanation, and so did everybody after them.
    The Pay button worked exactly once in the lifetime of the database.

    It went unnoticed because a test that pays one bill passes. tests/test_api.py
    now pays two.

    So: read the ids, keep the ones that are numeric after the prefix, and take
    the largest as a NUMBER. A reference shaped like the provider's own is
    skipped rather than crashing the parse.
    """
    numeric = 0
    for (candidate,) in db.query(Payment.payment_id).filter(Payment.payment_id.like("PAY-%")):
        tail = str(candidate).split("-", 1)[-1]
        if tail.isdigit():
            numeric = max(numeric, int(tail))
    return f"PAY-{numeric + 1:06d}"


@router.post("/bills/{bill_id}/pay", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def pay_bill(
    bill_id: str,
    payload: BillPaymentRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Record a payment against a bill.

    WHY THIS EXISTS
    ---------------
    The Pay button on the Bills page raised a toast reading "Payment initiated"
    and did nothing else: no request, no payment row, and the bill stayed
    unpaid for ever. SRS Section VI-iii puts payment records and outstanding
    balance in the Billing and Payment module, so the record was specified; only
    the write was missing.

    This is a book entry, not a card transaction. No money moves, and no payment
    provider is integrated: the platform records that a payment was made through
    one of the provider's channels, which is exactly what the Payment entity
    models and what the seeded data contains.
    """
    bill = db.get(Bill, bill_id)
    if bill is None or bill.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")

    if bill.status == "Paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This bill has already been paid.",
        )

    # WHAT IS ACTUALLY STILL OWED ON THIS BILL
    # ----------------------------------------
    # Not the face value. 845 of this provider's 5,400 invoices are part paid,
    # and the default here used to be `bill.amount`, so pressing Pay on one of
    # them charged the whole bill a second time.
    #
    # Measured: a subscriber owing 4,725,839 on a 20,711,549 bill pressed Pay
    # and 20,711,549 was recorded. The bill then held 36,697,259 against a face
    # value of 20,711,549, and the admin's total revenue rose by the full
    # 20,711,549 when the provider had been owed 4,725,839. Sixteen million
    # pounds of revenue that never came through the door, on one click.
    #
    # The balance on screen hid it, because `owed.py` clamps a negative balance
    # to zero: the customer saw the right thing and the accounts did not.
    received = paid_against(db, [bill.bill_id]).get(bill.bill_id, 0.0)
    still_owed = round(max(0.0, float(bill.amount) - received), 2)

    if still_owed <= 0:
        # The bill is covered but its status row says otherwise, which is the
        # state a pipeline re-run leaves behind: it rebuilds every bill from
        # the provider's file and cannot see a payment taken in the portal. The
        # customer was shown a Pay button and refused when they pressed it.
        # Correct the row here rather than arguing with them about it.
        bill.status = "Paid"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This bill is already settled in full.",
        )

    amount = round(float(payload.amount if payload.amount is not None else still_owed), 2)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A payment must be greater than zero.",
        )
    if amount > still_owed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Only {money(still_owed)} is still owed on this bill. "
                "A payment cannot be larger than that."
            ),
        )

    settled = amount >= still_owed

    payment = Payment(
        payment_id=_next_payment_id(db),
        customer_id=current_user.customer_id,
        bill_id=bill.bill_id,
        date=datetime.now(UTC).date(),
        amount=amount,
        method=payload.method.strip() or "Online Card",
        # A part payment is recorded as Partial so the payments page and the
        # risk model both see it for what it is.
        status="Completed" if settled else "Partial",
    )
    db.add(payment)

    if settled:
        bill.status = "Paid"

    db.commit()
    db.refresh(payment)

    # A paid bill should stop generating a reminder immediately, not at the
    # next unrelated refresh.
    try:
        alert_engine.refresh_for_customer(db, current_user.customer_id)
    except Exception:  # pragma: no cover, the payment is recorded either way
        db.rollback()

    return serialize_payment(payment)


@router.get("/bills/{bill_id}/pdf")
def download_bill(
    bill_id: str,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    The bill as a PDF.

    The PDF button on the Bills page used to raise a toast saying the file was
    being prepared, and prepare nothing. This renders the same document the
    page shows, from the stored row.
    """
    from app.reports.receipt import build_bill_pdf

    bill = db.get(Bill, bill_id)
    if bill is None or (
        bill.customer_id != current_user.customer_id and current_user.role != "admin"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")

    owner = db.get(Customer, bill.customer_id)
    payments = (
        db.query(Payment)
        .filter(Payment.bill_id == bill.bill_id)
        .order_by(Payment.date)
        .all()
    )

    payload = build_bill_pdf(bill, owner, payments)
    filename = f"{bill.bill_id}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@router.get("/payments", response_model=list[PaymentOut])
def get_payments(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    payments = (
        db.query(Payment)
        .filter(Payment.customer_id == current_user.customer_id)
        .order_by(Payment.date.desc())
        .all()
    )
    return [serialize_payment(payment) for payment in payments]


@router.get("/payments/{payment_id}/receipt")
def get_payment_receipt(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Download a payment receipt as a PDF.

    The "Payment receipts" output of the Billing & Payment Module (SRS VI-iii).
    A customer may only fetch receipts for their own payments; an admin may
    fetch any, since they handle billing enquiries.
    """
    payment = db.get(Payment, payment_id)

    if payment is None or (
        payment.customer_id != current_user.customer_id and current_user.role != "admin"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    customer = db.get(Customer, payment.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    bill = db.get(Bill, payment.bill_id) if payment.bill_id else None

    from app.reports.receipt import build_receipt_pdf

    pdf = build_receipt_pdf(payment, customer, bill)
    filename = f"receipt-{payment.payment_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
@router.get("/recommendations", response_model=list[RecommendationOut])
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    """Return stored recommendations, generating them on first access."""
    recommendations = (
        db.query(Recommendation)
        .filter(Recommendation.customer_id == current_user.customer_id)
        .order_by(Recommendation.completed, Recommendation.estimated_savings.desc())
        .all()
    )

    if not recommendations:
        recommender.refresh_for_customer(db, current_user.customer_id)
        recommendations = (
            db.query(Recommendation)
            .filter(Recommendation.customer_id == current_user.customer_id)
            .order_by(Recommendation.completed, Recommendation.estimated_savings.desc())
            .all()
        )

    return [serialize_recommendation(rec, lang) for rec in recommendations]


@router.patch("/recommendations/{rec_id}", response_model=RecommendationUpdateOut)
def mark_recommendation(
    rec_id: str,
    payload: RecommendationUpdate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Mark a recommendation complete. Accepts both "rec-12" and "12"."""
    raw_id = rec_id.removeprefix("rec-")
    if not raw_id.isdigit():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    rec = db.get(Recommendation, int(raw_id))
    if rec is None or rec.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    rec.completed = payload.completed
    db.commit()
    return {"id": f"rec-{rec.recommendation_id}", "completed": rec.completed}


@router.post("/recommendations/refresh", response_model=list[RecommendationOut])
def refresh_recommendations(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    """Re-run the recommendation engine against the latest consumption data."""
    recommender.refresh_for_customer(db, current_user.customer_id)
    recommendations = (
        db.query(Recommendation)
        .filter(Recommendation.customer_id == current_user.customer_id)
        .order_by(Recommendation.completed, Recommendation.estimated_savings.desc())
        .all()
    )
    return [serialize_recommendation(rec, lang) for rec in recommendations]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
@router.get("/alerts", response_model=list[AlertOut])
def get_alerts(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    alerts = (
        db.query(Alert)
        .filter(Alert.customer_id == current_user.customer_id)
        .order_by(Alert.date.desc(), Alert.alert_id.desc())
        .all()
    )
    return [serialize_alert(alert, lang) for alert in alerts]


@router.post("/alerts/refresh", response_model=list[AlertOut])
def refresh_alerts(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    """
    Re-run the alert engine against the latest data.

    The mirror of /recommendations/refresh. Without it, alerts could only ever
    come from the seeder, which is what made "Receive alerts" a page rather
    than a feature.
    """
    alert_engine.refresh_for_customer(db, current_user.customer_id)
    rows = (
        db.query(Alert)
        .filter(Alert.customer_id == current_user.customer_id)
        .order_by(Alert.date.desc(), Alert.alert_id.desc())
        .all()
    )
    return [serialize_alert(alert, lang) for alert in rows]


@router.patch("/alerts/{alert_id}", response_model=AlertUpdateOut)
def mark_alert(
    alert_id: str,
    payload: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """Mark an alert read or unread. Accepts both "a-12" and "12"."""
    raw_id = alert_id.removeprefix("a-")
    if not raw_id.isdigit():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert = db.get(Alert, int(raw_id))
    if alert is None or alert.customer_id != current_user.customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert.read = payload.read
    db.commit()
    return {"id": f"a-{alert.alert_id}", "read": alert.read}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def _profile_out(customer: Customer) -> dict:
    """
    One place that shapes the profile response.

    GET and PATCH have to return the same fields; writing the dict twice is how
    a new preference ends up readable through one of them and not the other.
    """
    return {
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "theme": customer.theme or "light",
        "language": customer.language or DEFAULT_LANGUAGE,
    }


@router.get("/profile", response_model=ProfileOut)
def get_profile(current_user: Customer = Depends(get_current_user)):
    return _profile_out(current_user)


@router.patch("/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    changes = payload.model_dump(exclude_unset=True)

    # Only 'light' and 'dark' are valid: reject anything else rather than
    # storing a value the frontend cannot render.
    if changes.get("theme") not in (None, "light", "dark"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Theme must be 'light' or 'dark'",
        )

    # Same rule for the language: a code the frontend has no catalogue for
    # would be stored happily and then show an untranslated interface on every
    # future sign-in, with nothing in the UI able to explain why.
    language = changes.get("language")
    if language is not None and language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Language must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
        )

    # Email is the login identity, so it has to stay unique.
    if changes.get("email"):
        new_email = str(changes["email"]).lower().strip()
        clash = (
            db.query(Customer)
            .filter(
                func.lower(Customer.email) == new_email,
                Customer.customer_id != current_user.customer_id,
            )
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another account already uses this email address",
            )
        changes["email"] = new_email

    for field, value in changes.items():
        if value is not None:
            setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return _profile_out(current_user)
