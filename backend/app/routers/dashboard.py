"""
Dashboard router, two composite endpoints.

Each returns one aggregated payload so a dashboard renders in a single
round-trip rather than a waterfall of requests.
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money
from app.ai import forecasting
from app.analytics import asof, owed
from app.core.deps import get_current_user, require_admin
from app.core.i18n import localize, request_language
from app.database import get_db
from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.recommendation import Recommendation
from app.routers.analytics import (_period_change, customer_base,
                                   customer_growth, revenue_trend, top_consumers)
from app.routers.billing import (
    serialize_alert,
    serialize_bill,
    serialize_payment,
    serialize_recommendation,
)
from app.routers.consumption import monthly_series
from app.schemas.dashboard import AdminDashboardOut, CustomerDashboardOut

router = APIRouter(prefix="/dashboard", tags=["Dashboards"])


def _mean_daily_kwh(db: Session, customer_id: str, start: datetime, end: datetime) -> float:
    """
    Average kWh per DAY over a window.

    Deliberately sums per calendar day before averaging. AVG(kwh) over the raw
    rows is wrong here: the consumption table holds hourly rows for the recent
    window and one aggregated row per day for older history, so a raw average
    compares ~0.7 kWh hourly readings against ~16 kWh daily totals. That made
    every customer look like they had cut usage by 95% and pinned the score at
    100 across the board.
    """
    rows = (
        db.query(func.date(Consumption.timestamp).label("d"),
                 func.sum(Consumption.kwh).label("total"))
        .filter(
            Consumption.customer_id == customer_id,
            Consumption.timestamp >= start,
            Consumption.timestamp < end,
        )
        .group_by("d")
        .all()
    )
    totals = [float(total or 0.0) for _, total in rows]
    return sum(totals) / len(totals) if totals else 0.0


def _comparison_anchor(db: Session, customer_id: str) -> datetime | None:
    """
    The point both comparison windows are measured back from.

    Midnight at the START of the newest reading's day, so every window covers
    whole calendar days and the newest day, which is usually only partly
    recorded, is left out.

    ANCHORED ON THE DATA, NOT THE CLOCK
    -----------------------------------
    Measuring back from `now` looks harmless and is not. Meter data always
    arrives behind real time, so the recent window silently loses its last few
    days while the window a year earlier keeps all thirty of its own. In summer
    the days it loses are the hottest and heaviest, so the customer is credited
    with a saving they did not make: with the readings a week behind, every
    account on this database reported a 20 to 40 percent drop that was nothing
    but the missing week. Anchoring on the newest reading compares thirty
    recorded days against thirty recorded days.
    """
    latest = (
        db.query(func.max(Consumption.timestamp))
        .filter(Consumption.customer_id == customer_id)
        .scalar()
    )
    if latest is None:
        return None

    # Midnight AFTER the newest reading's day. The windows below are half-open,
    # [start, anchor), so anchoring on the reading's own day excluded that very
    # reading, and with meters read once a month that is the whole of the most
    # recent month, which is why the saving score came back "not enough data"
    # for accounts holding eighteen months of history.
    anchor = datetime.combine(latest.date(), time.min) + timedelta(days=1)
    # A reading dated in the future must not push the window past today.
    today_start = datetime.combine(datetime.now(UTC).date(), time.min) + timedelta(days=1)
    return min(anchor, today_start)


def _energy_saving_score(db: Session, customer_id: str) -> dict:
    """
    0-100 score for how the customer's usage compares with their own past.

    Compared YEAR-ON-YEAR: the last 30 days against the same 30 days a year
    ago. Comparing against the preceding months instead would conflate
    seasonality with behaviour, in July every air-conditioned household looks
    worse than its February self, which says nothing about whether they are
    saving energy. Matching the calendar window cancels the season out.

    Falls back to the preceding 30 days when there is no data from last year.

    Returns {"score", "basis", "change_pct"}. `score` is None when there is
    nothing to compare against, and the caller is expected to say so rather
    than print a number.

    WHY IT RETURNS None INSTEAD OF A NEUTRAL 70
    -------------------------------------------
    It used to `return 70` in both of those cases. 70 is the midpoint of the
    scale, the value that means "using exactly as much as last year", so an
    account with no readings at all was being shown a specific, confident,
    entirely invented figure. Every newly registered customer saw 70/100, and
    the number never moved, because it was never computed. A score that cannot
    be calculated has to be absent, not defaulted: an invented 70 is
    indistinguishable on screen from a measured 70.
    """
    unknown = {"score": None, "basis": None, "change_pct": None}

    anchor = _comparison_anchor(db, customer_id)
    if anchor is None:
        return unknown

    recent = _mean_daily_kwh(db, customer_id, anchor - timedelta(days=30), anchor)
    if recent <= 0:
        return unknown

    # Same calendar window one year earlier.
    basis = "year"
    reference = _mean_daily_kwh(
        db,
        customer_id,
        anchor - timedelta(days=365 + 30),
        anchor - timedelta(days=365),
    )

    if reference <= 0:
        # Not enough history for year-on-year: use the previous month.
        basis = "month"
        reference = _mean_daily_kwh(
            db, customer_id, anchor - timedelta(days=60), anchor - timedelta(days=30)
        )

    if reference <= 0:
        return unknown

    # 70 is "same as last year". Using less scores higher, more scores lower.
    # Clamped to 5-99 so the number always reads as a score rather than a
    # saturated 0 or a suspicious perfect 100.
    ratio = recent / reference
    score = 70 - (ratio - 1.0) * 120
    return {
        "score": int(max(5, min(99, round(score)))),
        "basis": basis,
        "change_pct": round((ratio - 1.0) * 100, 1),
    }


MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _empty_month() -> dict:
    """Zero-value consumption point for an account with no readings yet."""
    today = datetime.now(UTC).date()
    return {"month": MONTH_ABBR[today.month - 1], "period": f"{today.year:04d}-{today.month:02d}",
            "kwh": 0.0, "cost": 0.0}


def _empty_bill() -> dict:
    """
    Zero-value bill for an account with no bills yet.

    Returned instead of null because the dashboard reads `.amount` and
    `.month` directly. Status is 'Paid' since nothing is owed.
    """
    today = datetime.now(UTC).date()
    return {
        "id": "-",
        "month": f"{MONTH_ABBR[today.month - 1]} {today.year}",
        "amount": 0.0,
        "due_date": today,
        "status": "Paid",
    }


@router.get("/customer", response_model=CustomerDashboardOut)
def customer_dashboard(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    """Composite payload for the customer home page."""
    customer_id = current_user.customer_id

    trend = monthly_series(db, customer_id)

    bills = (
        db.query(Bill)
        .filter(Bill.customer_id == customer_id)
        .order_by(Bill.due_date)
        .all()
    )
    # The NEWEST unpaid bill, not the oldest. `bills` is ordered by due date
    # ascending, so scanning forward returned the earliest debt on the account:
    # a customer several months behind was shown a bill from a year ago as his
    # "current" one, with last year's amount and last year's due date.
    unpaid = [bill for bill in reversed(bills) if bill.status != "Paid"]
    current_bill = unpaid[0] if unpaid else (bills[-1] if bills else None)

    payments = (
        db.query(Payment)
        .filter(Payment.customer_id == customer_id)
        .order_by(Payment.date.desc())
        .all()
    )
    recommendations = (
        db.query(Recommendation)
        .filter(
            Recommendation.customer_id == customer_id,
            Recommendation.completed.is_(False),
        )
        .order_by(Recommendation.estimated_savings.desc())
        .limit(3)
        .all()
    )
    alerts = (
        db.query(Alert)
        .filter(Alert.customer_id == customer_id)
        .order_by(Alert.date.desc(), Alert.alert_id.desc())
        .limit(3)
        .all()
    )

    # Face value less what has already been paid against each bill. Summing
    # the face value charged this customer again for his part payments and put
    # 7,962,610 on the card while the assistant, on the same account, said
    # 3,926,058. See app/analytics/owed.py.
    outstanding = owed.outstanding_for(db, customer_id)

    saving = _energy_saving_score(db, customer_id)

    return {
        # Never null: see the note on CustomerDashboardOut.
        "monthly_consumption": trend[-1] if trend else _empty_month(),
        "current_bill": serialize_bill(current_bill) if current_bill else _empty_bill(),
        "outstanding_balance": round(outstanding, 2),
        # Null when the account has nothing to compare against. The dashboard
        # says so rather than printing a made-up number.
        "energy_saving_score": saving["score"],
        "energy_saving_basis": saving["basis"],
        "energy_saving_change_pct": saving["change_pct"],
        "consumption_trend": trend,
        "monthly_bills": [serialize_bill(bill) for bill in bills],
        "payment_history": [serialize_payment(payment) for payment in payments],
        "recent_recommendations": [serialize_recommendation(rec, lang) for rec in recommendations],
        "recent_alerts": [serialize_alert(alert, lang) for alert in alerts],
    }


def _month_over_month(
    db: Session, when, amount, as_of: date
) -> tuple[float, float, tuple[int, int] | None]:
    """
    The newest COMPLETE calendar month, and the month before it.

    Complete matters. The provider's payments stop on 10 July, so July holds a
    third of a normal month's takings, and comparing it with a whole June put
    "-70%" on the revenue card. Revenue had not fallen by seventy per cent; the
    month was not over. That is the same class of mistake as the rolling
    thirty-day window this replaced, a plausible wrong number rather than an
    obviously empty one, and it deserves the same treatment.

    A month counts as complete when the data reaches past its last day. Anything
    later than that is still being written and is left out of the comparison.
    It still appears in the trend chart, where a short final bar reads as what
    it is.

    Returns (current, previous, (year, month) of current). Both totals are zero
    and the month is None when the table is empty, and `previous` alone is zero
    when there is only one month of history, which the caller reads as "no
    change to report" rather than as a fall to zero.
    """
    # Bucketed in Python rather than with a SQL date function: this runs on
    # SQLite in development and PostgreSQL in production, and the two spell
    # month-truncation differently. The consumption trend below does the same.
    months: dict[tuple[int, int], float] = {}
    for moment, value in db.query(when, amount).all():
        if moment is None:
            continue
        key = (moment.year, moment.month)
        months[key] = months.get(key, 0.0) + float(value or 0.0)

    if not months:
        return 0.0, 0.0, None

    def complete(key: tuple[int, int]) -> bool:
        year, month = key
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        return as_of >= last_day

    ordered = [key for key in sorted(months) if complete(key)]
    if not ordered:
        # Every month is still open, a first partial month of live data. Report
        # what there is rather than nothing, and leave the comparison empty.
        newest = sorted(months)[-1]
        return float(months[newest] or 0.0), 0.0, newest

    current = float(months[ordered[-1]] or 0.0)
    previous = float(months[ordered[-2]] or 0.0) if len(ordered) > 1 else 0.0
    return current, previous, ordered[-1]


@router.get("/admin", response_model=AdminDashboardOut)
def admin_dashboard(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """Composite payload for the executive analytics dashboard."""
    # Not the wall clock: the newest measurement the platform holds. The
    # supplied dataset ends before today, and every "last 30 days" window
    # measured from now would land in the gap and report zero. See
    # app/analytics/asof.py for why the data is not moved instead.
    at = asof.anchor(db)

    total_customers = int(
        db.query(func.count(Customer.customer_id)).filter(Customer.role == "customer").scalar() or 0
    )
    active_customers = int(
        db.query(func.count(Customer.customer_id))
        .filter(Customer.role == "customer", Customer.status == "Active")
        .scalar()
        or 0
    )
    total_revenue = float(
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).scalar() or 0.0
    )

    # Month over month, by CALENDAR MONTH rather than by a rolling 30 days.
    #
    # The meters here are read once a month, so a subscriber contributes one
    # timestamp per month and a 30-day window that happens to straddle two
    # reading dates catches a fraction of one month and none of the other. It
    # reported 22,974 kWh for a month whose real total was 86,470: not an
    # empty chart, which someone would question, but a plausible wrong number,
    # which nobody would. Whole months are the unit the data actually has.
    current_consumption, previous_consumption, consumption_month = _month_over_month(
        db, Consumption.timestamp, Consumption.kwh, at.as_of
    )
    consumption_change = (
        ((current_consumption - previous_consumption) / previous_consumption * 100)
        if previous_consumption > 0
        else 0.0
    )

    current_revenue, previous_revenue, _ = _month_over_month(
        db, Payment.date, Payment.amount, at.as_of
    )
    revenue_change = (
        ((current_revenue - previous_revenue) / previous_revenue * 100)
        if previous_revenue > 0
        else 0.0
    )

    # None when the data carries no joining dates at all, which is this
    # provider's case: his export is eighteen months of an already existing
    # customer base and `created_at` on a generated record is the month of the
    # subscriber's first invoice, the same month for all three hundred. The
    # growth chart already says so and draws nothing. The card beside it was
    # saying "+0.0%", which claims we looked and nobody joined, a different
    # and stronger statement than the one the data supports.
    # AND WHEN THERE ARE JOINING DATES, THE FIGURE IS A CHANGE, NOT A SHARE
    # ----------------------------------------------------------------------
    # This card was computing new-in-30-days over the whole base: a share of
    # the base, printed under an arrow that can point down, in a row where
    # every other card is a month-over-month change. It could never be
    # negative, so a shrinking customer base would have shown as growth.
    #
    # The window was wrong twice over as well. It had a lower bound and no
    # upper one, so "the last 30 days" ran from the anchor to whenever anybody
    # happened to be looking, 114 days by the time this was found. And the
    # anchor is the newest METER READING, while the values being counted are
    # record-creation dates: two clocks months apart, with nothing tying a
    # subscriber's joining date to when the reader last walked the street.
    #
    # The growth series is already a cumulative count by calendar month, which
    # makes the honest figure the change between its last two points, on the
    # same footing as revenue and consumption beside it.
    growth_series = customer_growth(db)
    customers_change = _period_change(growth_series, "customers")

    stats = {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "revenue": round(total_revenue, 2),
        "monthly_consumption": round(current_consumption, 1),
        "prediction_accuracy": forecasting.model_accuracy(db),
        "revenue_change": round(revenue_change, 1),
        "customers_change": round(customers_change, 1) if customers_change is not None else None,
        "consumption_change": round(consumption_change, 1),
        "consumption_period": (
            f"{consumption_month[0]:04d}-{consumption_month[1]:02d}" if consumption_month else None
        ),
        # Which day the month-based figures above are actually for, and
        # whether that is today. The interface prints it, so nobody reads a
        # June figure as August's.
        "as_of": at.as_of,
        "is_live": at.is_live,
    }

    # System-wide monthly consumption trend
    all_rows = db.query(Consumption.timestamp, Consumption.kwh, Consumption.cost).all()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    buckets: dict[tuple[int, int], dict[str, float]] = {}
    for timestamp, kwh, cost in all_rows:
        key = (timestamp.year, timestamp.month)
        bucket = buckets.setdefault(key, {"kwh": 0.0, "cost": 0.0})
        bucket["kwh"] += float(kwh or 0)
        bucket["cost"] += float(cost or 0)

    consumption_trend = [
        {
            "month": month_names[month - 1],
            "period": f"{year:04d}-{month:02d}",
            "kwh": round(values["kwh"], 1),
            "cost": round(values["cost"], 2),
        }
        for (year, month), values in sorted(buckets.items())[-12:]
    ]

    forecast = forecasting.generate_forecast(db)

    return {
        "stats": stats,
        "revenue_trend": revenue_trend(db),
        "customer_growth": growth_series,
        "customer_base": customer_base(db),
        "forecast_data": forecast["forecastData"],
        "consumption_trend": consumption_trend,
        "top_consumers": top_consumers(db),
        "recent_activities": [
            {**activity, "text": localize(activity["text"], lang), "time": localize(activity["time"], lang)}
            for activity in _recent_activities(db)
        ],
    }


def _recent_activities(db: Session, limit: int = 6) -> list[dict]:
    """Merge recent events from several tables into one activity feed."""
    now = datetime.now(UTC)
    events: list[tuple[datetime, dict]] = []

    for customer in (
        db.query(Customer)
        .filter(Customer.role == "customer")
        .order_by(Customer.created_at.desc())
        .limit(limit)
    ):
        created = customer.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        events.append(
            (
                created,
                {
                    "id": f"act-cust-{customer.customer_id}",
                    "text": f"New customer {customer.name} registered",
                    "type": "user",
                },
            )
        )

    # Ordered by id as well as date. `Payment.date` is a DATE with no time, so
    # every payment made today ties, the tiebreak is whatever the database
    # feels like, and the payment somebody just made frequently did not appear
    # in a feed headed "Recent Activities". Ids increase, so they settle it.
    for payment in (
        db.query(Payment)
        .order_by(Payment.date.desc(), Payment.payment_id.desc())
        .limit(limit)
    ):
        events.append(
            (
                datetime.combine(payment.date, datetime.min.time()).replace(tzinfo=UTC),
                {
                    "id": f"act-pay-{payment.payment_id}",
                    "text": (
                        f"Payment of {money(payment.amount)} processed for "
                        f"{payment.customer_id}"
                    ),
                    "type": "payment",
                },
            )
        )

    for anomaly in db.query(Anomaly).order_by(Anomaly.detected_at.desc()).limit(limit):
        detected = anomaly.detected_at
        if detected is None:
            continue
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=UTC)
        events.append(
            (
                detected,
                {
                    "id": f"act-anom-{anomaly.anomaly_id}",
                    "text": f"Anomaly flagged for {anomaly.customer_id} ({anomaly.type})",
                    "type": "alert",
                },
            )
        )

    events.sort(key=lambda item: item[0], reverse=True)

    activities = []
    for occurred_at, payload in events[:limit]:
        activities.append({**payload, "time": _humanize(now - occurred_at)})
    return activities


def _humanize(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days > 1 else ''} ago"
