"""
Admin analytics, customer management, business KPIs, regional stats, revenue.

Every endpoint here is guarded by `require_admin`, implementing the
Role-Based Access Control requirement from Section IX.
"""

import logging
from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import risk
from app.analytics import asof, owed
from app.config import settings
from app.core import registration_codes
from app.core.accounts import email_in_use
from app.core.deps import require_admin
from app.core.i18n import localize_all, month_year, request_language
from app.database import get_db
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.schemas.analytics import (
    BusinessKpisOut,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    DeleteResult,
    RegionalStatOut,
    RevenueOverviewOut,
    RiskSummaryOut,
)
from app.schemas.auth import RegistrationCodeOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin Analytics"])

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _whole_months(db: Session, buckets: dict[tuple[int, int], float]) -> list:
    """
    Monthly buckets in order, with a final partial month removed.

    WHY A PARTIAL MONTH CANNOT BE THE LAST BAR ON A CHART
    -----------------------------------------------------
    The provider's payments stop on 10 July 2026. Bucketed by calendar month,
    July holds ten days of takings, 760 million pounds, and sits on the chart
    beside a complete June of 2,533 million. Nothing about that bar is false and
    everybody who reads the chart draws the same conclusion from it, which is
    that revenue collapsed by seventy percent. What actually happened is that
    the file ended.

    The KPI cards were already fixed to report `last_complete_month`. The charts
    were not, so a card saying June sat above a chart whose last point was July.
    This puts the two on the same footing: whole months only, everywhere.

    A month counts as whole when the newest measurement in the database falls on
    or after its last day, so the current month appears as soon as it closes.
    """
    if not buckets:
        return []

    ordered = sorted(buckets.items())
    _, last_complete_end = asof.anchor(db).last_complete_month
    return [
        (key, value)
        for key, value in ordered
        if date(key[0], key[1], monthrange(key[0], key[1])[1]) <= last_complete_end
    ]


# ---------------------------------------------------------------------------
# Shared computations (reused by the admin dashboard router)
# ---------------------------------------------------------------------------
def regional_stats(db: Session) -> list[dict]:
    """Customers, revenue and consumption grouped by region."""
    customer_counts = dict(
        db.query(Customer.region, func.count(Customer.customer_id))
        .filter(Customer.role == "customer")
        .group_by(Customer.region)
        .all()
    )
    revenue = dict(
        db.query(Customer.region, func.coalesce(func.sum(Payment.amount), 0.0))
        .join(Payment, Payment.customer_id == Customer.customer_id)
        .group_by(Customer.region)
        .all()
    )
    consumption = dict(
        db.query(Customer.region, func.coalesce(func.sum(Consumption.kwh), 0.0))
        .join(Consumption, Consumption.customer_id == Customer.customer_id)
        .group_by(Customer.region)
        .all()
    )

    return [
        {
            "region": region or "Unassigned",
            "customers": int(count),
            "revenue": round(float(revenue.get(region, 0.0)), 2),
            "consumption": round(float(consumption.get(region, 0.0)), 1),
        }
        for region, count in sorted(customer_counts.items(), key=lambda item: -item[1])
    ]


def top_consumers(db: Session, limit: int = 5) -> list[dict]:
    """
    Highest-consuming customers over the most recent 30 days OF DATA.

    Anchored to the newest measurement rather than to the wall clock. With a
    dataset that ends before today, the wall-clock window is empty and this
    list silently ranks nobody. See app/analytics/asof.py.
    """
    at = asof.anchor(db)
    current_window = at.since(30)
    previous_window = at.since(60)

    current = dict(
        db.query(Consumption.customer_id, func.sum(Consumption.kwh))
        .filter(Consumption.timestamp >= current_window)
        .group_by(Consumption.customer_id)
        .all()
    )
    previous = dict(
        db.query(Consumption.customer_id, func.sum(Consumption.kwh))
        .filter(
            Consumption.timestamp >= previous_window,
            Consumption.timestamp < current_window,
        )
        .group_by(Consumption.customer_id)
        .all()
    )

    names = dict(db.query(Customer.customer_id, Customer.name).all())
    ranked = sorted(current.items(), key=lambda item: float(item[1] or 0), reverse=True)[:limit]

    results = []
    for customer_id, total in ranked:
        total = float(total or 0)
        prior = float(previous.get(customer_id) or 0)
        # None, not 0.0, when there is no earlier window to compare against.
        # A hand-read meter gives one reading a month, so the previous 30 days
        # frequently contain none at all, and "0.0%" beside a customer's name
        # was read on screen as "unchanged" when it meant "we cannot tell".
        # Three of the five top consumers were showing it.
        change = ((total - prior) / prior * 100) if prior > 0 else None
        results.append(
            {
                "name": names.get(customer_id, customer_id),
                "consumption": round(total, 1),
                "change": round(change, 1) if change is not None else None,
            }
        )
    return results


def revenue_trend(db: Session, months: int = 12) -> list[dict]:
    """Total payments received per calendar month."""
    rows = db.query(Payment.date, Payment.amount).all()

    buckets: dict[tuple[int, int], float] = {}
    for payment_date, amount in rows:
        key = (payment_date.year, payment_date.month)
        buckets[key] = buckets.get(key, 0.0) + float(amount or 0)

    ordered = _whole_months(db, buckets)[-months:]
    return [
        {"month": MONTH_NAMES[month - 1], "revenue": round(total, 2)}
        for (_, month), total in ordered
    ]


def consumption_trend(db: Session, months: int = 12) -> list[dict]:
    """System-wide kWh per calendar month."""
    rows = db.query(Consumption.timestamp, Consumption.kwh).all()

    buckets: dict[tuple[int, int], float] = {}
    for timestamp, kwh in rows:
        if timestamp is None:
            continue
        key = (timestamp.year, timestamp.month)
        buckets[key] = buckets.get(key, 0.0) + float(kwh or 0)

    ordered = _whole_months(db, buckets)[-months:]
    return [{"month": MONTH_NAMES[month - 1], "kwh": round(total, 1)} for (_, month), total in ordered]


def bill_count_trend(db: Session, months: int = 12) -> list[dict]:
    """Number of bills issued per calendar month, keyed on the due date."""
    rows = db.query(Bill.due_date).all()

    buckets: dict[tuple[int, int], int] = {}
    for (due,) in rows:
        if due is None:
            continue
        key = (due.year, due.month)
        buckets[key] = buckets.get(key, 0) + 1

    ordered = _whole_months(db, buckets)[-months:]
    return [{"month": MONTH_NAMES[month - 1], "count": count} for (_, month), count in ordered]


def payment_count_trend(db: Session, months: int = 12) -> list[dict]:
    """
    Number of payments received per calendar month.

    Separate from revenue_trend, which sums the amounts. The Analytics page
    drew a "Payment Trends" chart from a hardcoded twelve-point array whose
    last value was the mock data's customer count, so it was neither payments
    nor a trend.
    """
    rows = db.query(Payment.date).all()

    buckets: dict[tuple[int, int], int] = {}
    for (payment_date,) in rows:
        if payment_date is None:
            continue
        key = (payment_date.year, payment_date.month)
        buckets[key] = buckets.get(key, 0) + 1

    ordered = _whole_months(db, buckets)[-months:]
    return [{"month": MONTH_NAMES[month - 1], "count": count} for (_, month), count in ordered]


def _period_change(series: list[dict], field: str) -> float | None:
    """
    Percentage change between the last two points of a monthly series.

    Returns None rather than zero when there is no previous month to compare
    against: the Analytics page used to print four fixed percentages next to
    genuinely fetched figures, and "no comparison yet" has to be sayable.
    """
    if len(series) < 2:
        return None
    previous = float(series[-2].get(field, 0) or 0)
    if previous <= 0:
        return None
    latest = float(series[-1].get(field, 0) or 0)
    return round((latest - previous) / previous * 100, 1)


# One month holding this share of the whole customer base is not a month in
# which everybody joined; it is a stand-in date wearing a month's clothes.
PLACEHOLDER_SHARE = 0.9


def customer_growth(db: Session, months: int = 12) -> list[dict]:
    """
    Cumulative customer count at the end of each month.

    RETURNS AN EMPTY LIST WHEN THE DATA HAS NO GROWTH IN IT, ON PURPOSE
    ------------------------------------------------------------------
    The provider's export carries no join date. Not in subscribers.csv, which
    holds an id, a zone and a type; not in subscriptions.csv; not in meters.csv.
    What it holds is eighteen months of an ALREADY EXISTING customer base:
    every one of the 300 subscribers has all eighteen invoices, every one has a
    reading in the first month, and every meter already had a non-zero dial when
    the export begins, between 3 and 2,959 kWh. Nobody joined during it.

    `created_at` on a generated record is therefore the month of that
    subscriber's first invoice, which is the closest thing the data offers and
    is the same month for all 300. Charted, that drew a single bar of 300 in
    January 2025, which reads as three hundred people signing up at once. The
    data makes no such claim.

    One bar is not a growth curve. Below two distinct months this returns
    nothing and the dashboard says why, rather than drawing a shape that
    invents an event.

    AND TWO BARS ARE NOT ONE EITHER
    -------------------------------
    The "below two distinct months" test was one admin action away from
    failing. Registering a single customer through the admin form stamps
    `created_at` with today, which makes a second distinct month, which opened
    the guard: the chart then drew 300 in January 2025 and 301 in September
    2026, and the card printed a growth figure. The single test account is
    real; the three hundred beside it are still a placeholder, and putting them
    on the same axis makes the placeholder look like history.

    So the test is what it should always have been: whether the joining dates
    describe joining at all. A base that all arrived in one month did not, and
    one month holding nearly all of it is the signature of a stand-in date
    rather than of a business. The months are labelled with their year for the
    same reason: a series longer than a year drew two bars both labelled "Jan".
    """
    rows = db.query(Customer.created_at).filter(Customer.role == "customer").all()

    signups: dict[tuple[int, int], int] = {}
    for (created_at,) in rows:
        if created_at is None:
            continue
        key = (created_at.year, created_at.month)
        signups[key] = signups.get(key, 0) + 1

    if len(signups) < 2:
        return []

    total = sum(signups.values())
    if total and max(signups.values()) / total >= PLACEHOLDER_SHARE:
        return []

    running = 0
    series = []
    for key in sorted(signups):
        running += signups[key]
        series.append({"month": f"{MONTH_NAMES[key[1] - 1]} {key[0]}",
                       "customers": running})

    return series[-months:]


def customer_base(db: Session, months: int = 12) -> list[dict]:
    """
    How many subscribers were billed each month, and how many settled in full.

    THE CHART THAT REPLACED AN EMPTY CARD
    -------------------------------------
    "Customer growth" cannot be drawn from this data and the dashboard said so
    honestly, which left an executive screen with a paragraph of explanation
    where a chart should be. The explanation was right and the hole was still
    a hole.

    This is the question the same data CAN answer, and it is closer to what an
    owner wanted from that card anyway. The billed line is the size of the
    customer base month by month, measured from the invoices actually issued
    rather than from a joining date nobody recorded. The settled line is how
    many of those bills were paid in full.

    On this provider's eighteen months the first is flat at 300 and the second
    drifts from 256 down to 225 and back to 248. A flat line is not a failure
    of the chart: it is the finding. The base did not move, and the paying part
    of it did.
    """
    rows = (
        db.query(Invoice.billing_period, Invoice.invoice_id, Invoice.subscriber_id)
        .order_by(Invoice.billing_period)
        .all()
    )
    if not rows:
        return []

    # Bill ids are derived from invoice ids by the portal projection; reading
    # the status straight off the bill keeps this consistent with every other
    # screen rather than re-deciding what "settled" means here.
    paid = {
        bill_id
        for (bill_id,) in db.query(Bill.bill_id).filter(Bill.status == "Paid").all()
    }

    buckets: dict[tuple[int, int], dict[str, set | int]] = {}
    for period, invoice_id, subscriber_id in rows:
        if period is None:
            continue
        key = (period.year, period.month)
        bucket = buckets.setdefault(key, {"billed": set(), "settled": 0})
        bucket["billed"].add(subscriber_id)
        if f"BILL-INV{invoice_id.removeprefix('INV')}" in paid:
            bucket["settled"] += 1

    series = [
        {
            "month": f"{MONTH_NAMES[month - 1]} {year}",
            "billed": len(bucket["billed"]),
            "settled": bucket["settled"],
        }
        for (year, month), bucket in sorted(buckets.items())
    ]
    return series[-months:]


# ---------------------------------------------------------------------------
# Customer management
# ---------------------------------------------------------------------------
@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    customers = (
        db.query(Customer)
        .filter(Customer.role == "customer")
        .order_by(Customer.customer_id)
        .all()
    )
    # One grouped query for all three hundred, so every row shows what the
    # customer owes right now rather than what they owed when the records were
    # generated.
    balances = owed.outstanding_for_all(db)
    return [
        _serialize_customer(customer, balances.get(customer.customer_id, 0.0))
        for customer in customers
    ]


def _serialize_customer(customer: Customer, balance: float | None = None) -> dict:
    """
    One customer row.

    `balance` is passed in, computed from the bills and payments, rather than
    read from `customers.balance`. That column is a snapshot written when the
    identities were generated: a customer who settled a bill from the portal
    still showed the old figure on this screen for ever, while the risk panel
    and the revenue page next to it had already moved. Where no balance is
    supplied the stored column is the fallback, which is the right answer for a
    customer who has no bills at all.
    """
    return {
        "id": customer.customer_id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "region": customer.region,
        "plan": customer.plan,
        "status": customer.status,
        "consumption": round(float(customer.consumption or 0), 1),
        "balance": round(float(customer.balance or 0), 2) if balance is None else round(balance, 2),
        "registered": customer.is_claimed,
    }


def _get_or_404(db: Session, customer_id: str) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    customer = _get_or_404(db, customer_id)
    return _serialize_customer(customer, owed.outstanding_for(db, customer_id))


# ---------------------------------------------------------------------------
# Manage Customer Accounts: Add / Update / Deactivate / Delete
#
# Implements the "Manage Customer Accounts" use case from the Use Case Model
# («include» Add / Update / Deactivate / Search). Search and pagination are
# handled client-side by CustomerManagement.tsx over the full list.
# ---------------------------------------------------------------------------
@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """Add a customer account."""
    email = str(payload.email).lower().strip()
    if email_in_use(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A customer with this email already exists",
        )

    # The provider's own account number, as the SRS specifies.
    customer_id = payload.customer_id.strip().upper()
    if db.get(Customer, customer_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            # Fixed wording, so the interface can show it in the reader's
            # language (it is a catalogue phrase); the ID is in the form.
            detail="This Customer ID is already in use",
        )

    customer = Customer(
        customer_id=customer_id,
        name=payload.name.strip(),
        email=email,
        # No password: the admin creates the customer RECORD, and the customer
        # registers for portal access themselves using this Customer ID. A
        # shared default here would give every admin-created account the same
        # known credentials.
        password_hash="",
        role="customer",
        phone=(payload.phone or "").strip() or None,
        address=(payload.address or "").strip() or None,
        region=(payload.region or "Unassigned").strip(),
        plan=payload.plan or "Residential",
        status="Active",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Give the account a meter history so it is not an empty row in every chart.
    if settings.PROVISION_DEMO_DATA:
        try:
            from app.pipeline.provision import provision_customer

            provision_customer(db, customer)
            db.refresh(customer)
        except Exception:
            logger.exception("Provisioning failed for %s", customer.customer_id)
            db.rollback()

    return _serialize_customer(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """Update a customer's details."""
    customer = _get_or_404(db, customer_id)
    changes = payload.model_dump(exclude_unset=True)

    if "email" in changes and changes["email"]:
        email = str(changes["email"]).lower().strip()
        # Staff (users) and customers share one pool of sign-in emails.
        if email_in_use(db, email, exclude_id=customer_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another customer already uses this email",
            )
        changes["email"] = email

    if "status" in changes and changes["status"] not in (None, "Active", "Suspended", "Inactive"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status must be Active, Suspended or Inactive",
        )

    for field, value in changes.items():
        if value is not None:
            setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return _serialize_customer(customer)


@router.post("/customers/{customer_id}/deactivate", response_model=CustomerOut)
def deactivate_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_admin),
):
    """
    Deactivate an account, the "Deactivate" use case.

    Suspends access but keeps every consumption reading, bill and payment.
    This is what a utility actually does: billing records must be retained,
    so a closed account is suspended, never erased.
    """
    customer = _get_or_404(db, customer_id)
    if customer.customer_id == admin.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    customer.status = "Suspended"
    db.commit()
    db.refresh(customer)
    return _serialize_customer(customer)


@router.post("/customers/{customer_id}/activate", response_model=CustomerOut)
def activate_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """Reactivate a suspended or inactive account."""
    customer = _get_or_404(db, customer_id)
    customer.status = "Active"
    db.commit()
    db.refresh(customer)
    return _serialize_customer(customer)


@router.post(
    "/customers/{customer_id}/registration-code",
    response_model=RegistrationCodeOut,
    status_code=status.HTTP_201_CREATED,
)
def issue_registration_code(
    customer_id: str,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_admin),
):
    """
    Issue a one-time registration code for an account nobody has registered yet.

    The customer needs it, with the Customer ID, to register for the portal.
    It is returned here once and stored only as a hash; issuing a new code
    replaces the previous one. For many accounts at once, for printing on the
    bills, use scripts/issue_registration_codes.py.
    """
    customer = _get_or_404(db, customer_id)
    if customer.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration codes are only issued for customer accounts",
        )
    if customer.is_claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is already registered",
        )
    if customer.status in ("Inactive", "Suspended"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reactivate this account before issuing a registration code",
        )

    code, expires_at = registration_codes.issue(customer)
    db.commit()
    logger.info("Registration code issued for %s by %s", customer.customer_id, admin.customer_id)
    return RegistrationCodeOut(
        customer_id=customer.customer_id, registration_code=code, expires_at=expires_at
    )


@router.delete("/customers/{customer_id}", response_model=DeleteResult)
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    admin: Customer = Depends(require_admin),
):
    """
    Permanently delete a customer and everything belonging to them.

    Destructive and irreversible: the cascade removes their consumption
    history, bills, payments, recommendations, alerts, anomalies and chats.
    Prefer /deactivate unless the record genuinely must be erased.
    """
    customer = _get_or_404(db, customer_id)

    if customer.customer_id == admin.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )
    if customer.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrator accounts cannot be deleted from this screen",
        )

    # Count before deleting so the response can report what was removed.
    consumption_rows = int(
        db.query(func.count(Consumption.consumption_id))
        .filter(Consumption.customer_id == customer_id).scalar() or 0
    )
    bill_rows = int(
        db.query(func.count(Bill.bill_id))
        .filter(Bill.customer_id == customer_id).scalar() or 0
    )
    payment_rows = int(
        db.query(func.count(Payment.payment_id))
        .filter(Payment.customer_id == customer_id).scalar() or 0
    )

    # Payments reference bills, so clear them before the ORM cascade runs.
    db.query(Payment).filter(Payment.customer_id == customer_id).delete(synchronize_session=False)
    db.flush()

    # relationship(cascade="all, delete-orphan") removes the rest.
    db.delete(customer)
    db.commit()

    return {
        "id": customer_id,
        "deleted": True,
        "removed_consumption_rows": consumption_rows,
        "removed_bills": bill_rows,
        "removed_payments": payment_rows,
    }


# ---------------------------------------------------------------------------
# Business KPIs / regional / revenue
# ---------------------------------------------------------------------------
@router.get("/analytics/kpis", response_model=BusinessKpisOut)
def business_kpis(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    total_revenue = float(
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).scalar() or 0.0
    )
    total_consumption = float(
        db.query(func.coalesce(func.sum(Consumption.kwh), 0.0)).scalar() or 0.0
    )

    revenue_series = revenue_trend(db)
    payment_series = payment_count_trend(db)
    consumption_series = consumption_trend(db)
    bills_series = bill_count_trend(db)

    return {
        "revenue": round(total_revenue, 2),
        "consumption": round(total_consumption, 1),
        "bills": int(db.query(func.count(Bill.bill_id)).scalar() or 0),
        "payments": int(db.query(func.count(Payment.payment_id)).scalar() or 0),
        "top_consumers": top_consumers(db),
        "regional_stats": regional_stats(db),

        # The series and the month-on-month changes the Analytics page draws.
        # It previously used hardcoded arrays and four fixed percentages, one
        # of which was negative and still rendered green.
        "revenue_trend": revenue_series,
        "payment_trend": payment_series,
        "changes": {
            "revenue": _period_change(revenue_series, "revenue"),
            "consumption": _period_change(consumption_series, "kwh"),
            "bills": _period_change(bills_series, "count"),
            "payments": _period_change(payment_series, "count"),
        },
    }


@router.get("/analytics/risk", response_model=RiskSummaryOut)
def payment_risk(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """
    Payment-default risk across the customer base, the early-warning system
    the Proposal problem statement asks for, and the "Risk notifications"
    output listed in SRS Section VI-vii.

    Every account is scored, riskiest first, each with the reasons behind its
    score so staff can act on the finding rather than trust a bare number.
    """
    summary = risk.portfolio_summary(db)
    for row in summary["customers"]:
        row["reasons"] = localize_all(row["reasons"], lang)
    return summary


@router.get("/analytics/regional", response_model=list[RegionalStatOut])
def regional(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    return regional_stats(db)


@router.get("/revenue/overview", response_model=RevenueOverviewOut)
def revenue_overview(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    statuses = dict(
        db.query(Bill.status, func.count(Bill.bill_id)).group_by(Bill.status).all()
    )

    # Real money figures for the four cards on the Revenue page. They were
    # computed in the browser as `lastMonthRevenue * 0.964`, an invented 96.4%
    # collection rate, and then multiplied by 1000, so every figure on that
    # page was both fabricated and a thousand times too large.
    # "This month" is the newest WHOLE month the data covers, and the same one
    # for both cards. Not the calendar month, because the dataset ends before
    # today; and not simply the newest month with anything in it, because that
    # one is usually half-written. Anchored on the data, this page showed
    # "Billed This Month 0" beside "Collected This Month 760.2M": his invoices
    # stop in June and his payments run ten days into July, so the two cards
    # were reporting different months and one of them was empty. See
    # app/analytics/asof.py.
    month_start, month_end = asof.anchor(db).last_complete_month

    collected_this_month = float(
        db.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(Payment.date >= month_start, Payment.date <= month_end)
        .scalar()
        or 0.0
    )
    billed_this_month = float(
        db.query(func.coalesce(func.sum(Bill.amount), 0.0))
        .filter(Bill.due_date >= month_start, Bill.due_date <= month_end)
        .scalar()
        or 0.0
    )
    # Same correction as the customer dashboard: part payments were being
    # billed twice. This reported 9.87 billion against a true 4.17 billion,
    # which is total billed minus total collected to the pound.
    outstanding_total = owed.outstanding_total(db)
    total_revenue = float(
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).scalar() or 0.0
    )

    return {
        "revenue_trend": revenue_trend(db),
        "regional_stats": regional_stats(db),
        "billing_statuses": [
            {"status": name, "count": int(statuses.get(name, 0))}
            for name in ("Paid", "Pending", "Overdue")
        ],
        "billed_this_month": round(billed_this_month, 2),
        "collected_this_month": round(collected_this_month, 2),
        # WHICH month those two cards are actually for.
        #
        # They were labelled "Billed This Month" and "Collected This Month" and
        # said nothing about which month that was. It is the last COMPLETE one,
        # which against this data is June 2026 while the calendar says August.
        # So a payment somebody records today correctly does not appear on them,
        # and the provider watching for it concludes the screen is broken. The
        # month is now printed under the figure, and `is_current` says whether
        # it is the month we are in.
        "period_label": month_year(month_start.strftime("%B %Y"), lang),
        "period_is_current": month_start == date.today().replace(day=1),
        "outstanding_total": round(outstanding_total, 2),
        "total_revenue": round(total_revenue, 2),
    }
