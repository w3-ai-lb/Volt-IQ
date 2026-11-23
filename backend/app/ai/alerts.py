"""
AI Module, Alert Engine.

The Proposal names the deliverable "Personalized recommendation **and alert**
engine", and "Receive alerts" is a Customer Portal feature in SRS Section III-i.
Recommendations tell a customer what to change; alerts tell them what just
happened and needs attention now.

Four signals, each traceable to a row in the customer's own data:

  high-usage   consumption over the last 30 days against that customer's own
               recent baseline, not a fixed kWh threshold, which would flag
               every large household and no small one
  payment      a bill falling due, or already overdue
  anomaly      a finding the detector persisted, promoted to the customer's feed
  low-usage    consumption down against the same baseline, so the feed carries
               good news too and not only warnings

Regeneration is idempotent. Each alert has a stable key of type + title, so
re-running updates the existing row instead of stacking duplicates, and an
alert whose condition no longer holds is withdrawn unless the customer has
already read it, a reminder to pay a bill should disappear once it is paid,
but a notice they have seen stays in their history.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money
from app.analytics import asof, owed
from app.models.alert import Alert
from app.ai.anomaly import MONTHLY_TYPE
from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.notification_preference import (
    DEFAULTS as PREFERENCE_DEFAULTS,
    PREFERENCE_FOR_ALERT_TYPE,
    NotificationPreference,
)

logger = logging.getLogger(__name__)

# Compare the most recent 30 days against the 90 days before it. Used only for
# customers whose meters actually report more than once a month; see
# `_usage_alerts` for what happens otherwise.
RECENT_DAYS = 30
BASELINE_DAYS = 90

# For a hand-read meter, the comparison is between READINGS, not between spans
# of days: the newest reading against the mean of this many before it.
BASELINE_READINGS = 3

# Below this the comparison is noise rather than a trend worth alerting on.
MIN_BASELINE_KWH = 5.0

HIGH_USAGE_THRESHOLD = 0.20     # +20% over baseline
LOW_USAGE_THRESHOLD = -0.15     # -15% under baseline
DUE_SOON_DAYS = 7

# Anomalies older than this are history, not news.
ANOMALY_WINDOW_DAYS = 45

_SEVERITY_FOR_ANOMALY = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "info",
}


def _today() -> date:
    return datetime.now(UTC).date()


def _day(value: date | datetime) -> str:
    """'8 Jun 2026': a date as the alerts write it, without a leading zero."""
    return f"{value.day} {value:%b %Y}"


def _kwh_between(db: Session, customer_id: str, start: datetime, end: datetime) -> float:
    total = (
        db.query(func.coalesce(func.sum(Consumption.kwh), 0.0))
        .filter(
            Consumption.customer_id == customer_id,
            Consumption.timestamp >= start,
            Consumption.timestamp < end,
        )
        .scalar()
    )
    return float(total or 0.0)


def _daily_rates(db: Session, customer_id: str) -> list[tuple[date, float]]:
    """
    Every reading as (date, kWh per day), newest first.

    A hand-read meter records one number a month, and that number is a whole
    month's consumption stamped on the day somebody photographed the dial. The
    intervals are not equal: in this provider's data they run from 24 to 40 days
    apart, because the meter reader gets to a street when he gets to it.

    So each reading is divided by the days it actually covers, which is the gap
    since the reading before it. Two readings a month apart are then comparable
    even though one covered 24 days and the other 40. The oldest reading has no
    predecessor and therefore no rate, so it is dropped.
    """
    rows = (
        db.query(Consumption.timestamp, Consumption.kwh)
        .filter(Consumption.customer_id == customer_id)
        .order_by(Consumption.timestamp.desc())
        .all()
    )
    rates: list[tuple[date, float]] = []
    for newer, older in zip(rows, rows[1:]):
        days = (newer[0] - older[0]).days
        if days <= 0:
            continue
        rates.append((newer[0].date(), float(newer[1] or 0.0) / days))
    return rates


def _same_month_last_year(rates: list[tuple[date, float]], when: date) -> float | None:
    """
    This customer's rate in the same calendar month a year before `when`.

    WHY THE COMPARISON IS TO LAST YEAR AND NOT TO LAST MONTH
    -------------------------------------------------------
    Comparing June against March, April and May told 236 of 300 subscribers
    that their consumption was above their usual level, median +56%, and
    advised each of them to check for an appliance left running. The arithmetic
    was right and the conclusion was nonsense: it was June in Lebanon. What the
    alert had actually detected was summer.

    An alert that fires for four out of five customers at once is not telling
    anybody anything about their own household. Measuring June against the
    previous June leaves the season in both halves of the comparison, so what
    is left is the part that is about this customer.

    Returns None when there is no reading in that month, which is the case for
    anyone with less than a year of history. The caller falls back to the
    trailing months and says so.
    """
    year, month = (when.year - 1, when.month)
    for reading_date, rate in rates:
        if reading_date.year == year and reading_date.month == month:
            return rate
    return None


def _usage_alerts(db: Session, customer_id: str) -> list[dict]:
    """
    Is this customer using more than they usually do?

    TWO WAYS OF ASKING, BECAUSE THERE ARE TWO KINDS OF METER
    -------------------------------------------------------
    This used to be a single 30-day window against the 90 days before it,
    anchored on the customer's newest reading. Anchoring fixed the windows
    landing in the gap after the data ends. It did not fix the arithmetic.

    A 30-day window over a meter read once a month contains one reading, or two,
    or none, depending on nothing more than which day of the month the reader
    happened to call. Subscriber GEN-00007's window caught two readings, 9 May
    and 7 June, and the 90-day baseline behind it caught two more and divided
    them by three. The alert told him he had used 379% more than usual. His
    consumption had risen from about 59 kWh a month to 102: a real rise, worth
    telling him about, and about +73%. The screen was wrong by a factor of five,
    in the alarming direction, about somebody's electricity bill.

    So the window is chosen by what the meter actually reports:

      more than once a day   the original 30-versus-90-day comparison, which is
                             the right question for a meter that reports
                             continuously and stays right if smart meters are
                             fitted later

      once a month           the newest reading against the mean of the three
                             before it, each divided by the days it covers, so
                             unequal reading intervals cannot masquerade as a
                             change in consumption

    Both are anchored on the customer's own newest reading, never the wall
    clock, for the reason set out in app/analytics/asof.py.
    """
    anchor_moment = asof.customer_anchor(db, customer_id)

    if asof.has_intraday(db, customer_id):
        recent_start = anchor_moment - timedelta(days=RECENT_DAYS)
        baseline_start = recent_start - timedelta(days=BASELINE_DAYS)

        recent = _kwh_between(db, customer_id, recent_start, anchor_moment)
        baseline_total = _kwh_between(db, customer_id, baseline_start, recent_start)
        baseline = baseline_total * (RECENT_DAYS / BASELINE_DAYS)
        # Literally the last thirty days, because the meter reports daily.
        period = "in the last 30 days"
        against = "than your typical level for the same length of time, which was {base} kWh"
        caveat = ""
    else:
        rates = _daily_rates(db, customer_id)
        if len(rates) < 3:
            # One reading cannot be compared with anything, and two make a
            # baseline of one. Neither is enough to tell somebody their usage
            # has changed, so nothing is said.
            return []

        latest_date, latest_rate = rates[0]
        year_ago = _same_month_last_year(rates, latest_date)
        if year_ago is not None and year_ago > 0:
            baseline_rate = year_ago
            against = f"than you used in {latest_date:%B} last year, when it was {{base}} kWh"
            caveat = ""
        else:
            preceding = [rate for _, rate in rates[1:1 + BASELINE_READINGS]]
            baseline_rate = sum(preceding) / len(preceding)
            against = "than the average of your recent months, which was {base} kWh"
            caveat = " Until you have a year of history, that is the best comparison available."

        # Stated per 30 days so the customer reads a monthly figure rather than
        # a rate. The comparison itself was made per day.
        recent = latest_rate * RECENT_DAYS
        baseline = baseline_rate * RECENT_DAYS
        # Named, not called "the last 30 days". The reading is weeks old by the
        # time anyone reads the alert, and a customer who checks the date on his
        # own bill should find the same month the alert is talking about.
        period = f"in the month to {_day(latest_date)}"

    if baseline < MIN_BASELINE_KWH or recent <= 0:
        # Not enough history to say anything honest about a trend.
        return []

    change = (recent - baseline) / baseline
    compared = against.format(base=f"{baseline:,.0f}")

    if change >= HIGH_USAGE_THRESHOLD:
        return [
            {
                "type": "high-usage",
                "title": "Your consumption is above your usual level",
                "message": (
                    f"You used {recent:,.0f} kWh {period}. That is "
                    f"{change * 100:.0f}% more {compared}.{caveat} Check for an appliance "
                    "left running, or cooling that is working harder than usual."
                ),
                "severity": "warning",
            }
        ]

    if change <= LOW_USAGE_THRESHOLD:
        return [
            {
                "type": "low-usage",
                "title": "Your consumption is down",
                "message": (
                    f"You used {recent:,.0f} kWh {period}. That is "
                    f"{abs(change) * 100:.0f}% less {compared}.{caveat} "
                    "Whatever you changed is working."
                ),
                "severity": "success",
            }
        ]

    return []


def _billing_alerts(db: Session, customer_id: str) -> list[dict]:
    """
    Remind about bills that are due soon, and flag those already overdue.

    WHAT THE AMOUNTS ARE
    --------------------
    What is still owed on each bill, not its face value. A part-paid bill used
    to be quoted in full ("1 unpaid bill totalling 7,790,359 LBP" when
    3,571,954 was left), charging the customer again for money already
    received. Same rule as everywhere else (app/analytics/owed.py).

    WHY DATES AND NOT "N DAYS AGO"
    ------------------------------
    The message is stored. "Due 592 days ago" was true on the day it was
    written and wrong every day after, and because the wording changed daily,
    every refresh marked an alert the customer had already read as unread
    again. A date stays true.
    """
    today = _today()
    alerts: list[dict] = []

    unpaid = (
        db.query(Bill)
        .filter(Bill.customer_id == customer_id, Bill.status != "Paid")
        .order_by(Bill.due_date)
        .all()
    )
    received = dict(
        db.query(Payment.bill_id, func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(Payment.customer_id == customer_id, Payment.bill_id.isnot(None))
        .group_by(Payment.bill_id)
        .all()
    )
    left = {b.bill_id: owed.owed_on(b, received.get(b.bill_id, 0.0)) for b in unpaid}
    # A bill marked unpaid with nothing actually left on it (an overpayment
    # recorded against it, say) is not something to remind anybody about.
    unpaid = [b for b in unpaid if left[b.bill_id] > 0]

    overdue = [b for b in unpaid if b.due_date < today]
    # Every open bill gets a notice, not only ones inside a narrow window. An
    # unpaid bill is the single most useful thing the alerts page can tell a
    # customer, and gating it on "due within a week" meant somebody with a bill
    # due in ten days was shown "nothing needs your attention": true of the
    # alert rules, and misleading about their account.
    upcoming = [b for b in unpaid if b.due_date >= today]

    if overdue:
        total = sum(left[b.bill_id] for b in overdue)
        oldest = min(b.due_date for b in overdue)
        if len(overdue) > 1:
            message = (
                f"{len(overdue)} unpaid bills with {money(total)} still to pay. The oldest was "
                f"due on {_day(oldest)}. Please settle them to avoid a service interruption."
            )
        else:
            message = (
                f"1 unpaid bill with {money(total)} still to pay. It was due on {_day(oldest)}. "
                "Please settle it to avoid a service interruption."
            )
        alerts.append(
            {
                "type": "payment",
                "title": "You have an overdue bill",
                "message": message,
                "severity": "error",
            }
        )

    if upcoming:
        nearest = upcoming[0]
        days = (nearest.due_date - today).days
        soon = days <= DUE_SOON_DAYS
        remaining = left[nearest.bill_id]
        if remaining < float(nearest.amount or 0.0):
            to_pay = f"{money(remaining)} still to pay of {money(nearest.amount)}"
        else:
            to_pay = f"{money(remaining)} to pay"
        alerts.append(
            {
                "type": "payment",
                "title": "Payment due soon" if soon else "Your bill is ready",
                "message": (
                    f"Your {nearest.month} bill is due on {_day(nearest.due_date)}, "
                    f"with {to_pay}."
                ),
                "severity": "info",
            }
        )

    return alerts


def _anomaly_alerts(db: Session, customer_id: str) -> list[dict]:
    """
    Surface recent unresolved anomalies in the customer's own feed.

    Grouped by anomaly type rather than one alert per finding: a meter that
    misreports for a week produces seven anomalies, and seven near-identical
    alerts would bury everything else in the feed. One alert per type, carrying
    the count and the worst severity seen, says the same thing once.
    """
    # Measured back from the customer's newest reading, not from today. An
    # anomaly is stamped with the day of the reading that caused it, so a
    # 45-day window run from the wall clock sits entirely after the end of the
    # data and finds nothing. That failure is silent: the feed simply never
    # carries an anomaly, and a screen that never fires looks like a screen
    # with nothing to report.
    since = asof.customer_anchor(db, customer_id) - timedelta(days=ANOMALY_WINDOW_DAYS)
    rows = (
        db.query(Anomaly)
        .filter(
            Anomaly.customer_id == customer_id,
            Anomaly.resolved.is_(False),
            Anomaly.detected_at >= since,
        )
        .order_by(Anomaly.detected_at.desc())
        .all()
    )
    if not rows:
        return []

    rank = {"info": 0, "success": 0, "warning": 1, "error": 2}
    grouped: dict[str, list[Anomaly]] = {}
    for row in rows:
        grouped.setdefault(row.type, []).append(row)

    alerts: list[dict] = []
    for anomaly_type, found in grouped.items():
        latest = found[0]                       # already ordered newest first
        severity = max(
            (_SEVERITY_FOR_ANOMALY.get(f.severity, "warning") for f in found),
            key=lambda s: rank.get(s, 1),
        )
        if anomaly_type == MONTHLY_TYPE:
            # The monthly model's own description is written for the analyst
            # ("cv=2.32", "trend_pct=-63.87"). The customer is told what it
            # means for him, in words, and what to do about it.
            message = (
                f"Your monthly readings up to {_day(latest.detected_at)} stand out against "
                "those of similar accounts. If this does not match how you used electricity, "
                "contact support so the meter can be checked."
            )
        elif len(found) == 1:
            message = (
                f"{latest.description} Recorded on {_day(latest.detected_at)}. If this does "
                "not match what you were doing, contact support."
            )
        else:
            message = (
                f"{len(found)} unusual readings in the last {ANOMALY_WINDOW_DAYS} days, "
                f"the most recent on {_day(latest.detected_at)}. {latest.description} "
                "If this does not match what you were doing, contact support."
            )

        alerts.append(
            {
                "type": "anomaly",
                "title": f"Unusual reading detected: {anomaly_type}",
                "message": message,
                "severity": severity,
            }
        )

    alerts.sort(key=lambda a: rank.get(a["severity"], 1), reverse=True)
    return alerts[:3]


def _enabled_types(db: Session, customer_id: str) -> set[str]:
    """
    The alert types this customer has asked to receive.

    An account with no preferences row receives everything, which is the
    default for anyone who has never opened Settings.
    """
    row = db.get(NotificationPreference, customer_id)
    if row is None:
        settings_map = PREFERENCE_DEFAULTS
    else:
        settings_map = {
            "high_usage": row.high_usage,
            "bill_reminders": row.bill_reminders,
            "anomalies": row.anomalies,
            "savings_milestones": row.savings_milestones,
        }

    return {
        alert_type
        for alert_type, field in PREFERENCE_FOR_ALERT_TYPE.items()
        if settings_map.get(field, True)
    }


def generate_alerts(db: Session, customer_id: str) -> list[dict]:
    """
    Every alert currently warranted for this customer, most urgent first.

    Filtered by the customer's notification preferences. The filter is applied
    here rather than inside each signal so that one place decides what a
    customer sees, and a signal added later is covered by default.
    """
    alerts = (
        _anomaly_alerts(db, customer_id)
        + _billing_alerts(db, customer_id)
        + _usage_alerts(db, customer_id)
    )

    enabled = _enabled_types(db, customer_id)
    alerts = [alert for alert in alerts if alert["type"] in enabled]

    order = {"error": 0, "warning": 1, "info": 2, "success": 3}
    alerts.sort(key=lambda a: order.get(a["severity"], 4))
    return alerts


def refresh_for_customer(db: Session, customer_id: str, commit: bool = True) -> list[Alert]:
    """
    Bring stored alerts in line with what the data now says.

    Existing rows are updated in place so a customer does not lose the read flag
    on an alert that is still valid, and a condition that has cleared withdraws
    its alert unless it has already been read.
    """
    wanted = {(a["type"], a["title"]): a for a in generate_alerts(db, customer_id)}

    existing = db.query(Alert).filter(Alert.customer_id == customer_id).all()
    seen: set[tuple[str, str]] = set()
    today = _today()

    for row in existing:
        key = (row.type, row.title)
        payload = wanted.get(key)

        if payload is None:
            # No longer warranted. Unread alerts are withdrawn; read ones stay
            # as history, because the customer has already acted on them.
            if not row.read:
                db.delete(row)
            continue

        seen.add(key)
        # Refresh the wording: the figures inside it have moved on.
        if row.message != payload["message"] or row.severity != payload["severity"]:
            row.message = payload["message"]
            row.severity = payload["severity"]
            row.date = today
            row.read = False

    created: list[Alert] = []
    for key, payload in wanted.items():
        if key in seen:
            continue
        record = Alert(customer_id=customer_id, date=today, read=False, **payload)
        db.add(record)
        created.append(record)

    if commit:
        db.commit()
    return created


def refresh_all(db: Session) -> int:
    """
    Regenerate alerts for every customer. Called after a data load, alongside
    the recommender rebuild, so alerts reflect the newly ingested readings.
    """
    total = 0
    customer_ids = [row[0] for row in db.query(Customer.customer_id).all()]
    for customer_id in customer_ids:
        try:
            total += len(refresh_for_customer(db, customer_id, commit=False))
        except Exception:
            logger.exception("Alert generation failed for %s", customer_id)
            db.rollback()
    db.commit()
    logger.info("Alert engine: %d new alerts across %d customers", total, len(customer_ids))
    return total
