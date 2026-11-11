"""
Which moment the platform's dashboards should call "now".

THE PROBLEM THIS SOLVES
-----------------------
Every figure on the admin dashboard was a window measured backwards from the
wall clock: consumption in the last 30 days, revenue in the last 30 days,
highest consumers in the last 30 days. That is right when data arrives
continuously and wrong the moment it does not.

The supervisor's dataset runs January 2025 to June 2026 and today is later
than that. Anchored to the wall clock, every one of those windows lands in a
gap and returns zero, and a dashboard reading "0 kWh this month" is reporting
a quiet month at the generators rather than the end of a file. The number is
not merely useless; it is wrong in a way that looks like a finding.

So the anchor is the newest measurement the platform actually holds, and the
payload says which day that is. `app/routers/ishtirak.py` already took this
decision for the generator dashboard; this is the same decision for the
platform's own, so the two halves of the system agree about what "now" means.

WHY NOT SHIFT THE DATA FORWARD INSTEAD
--------------------------------------
Because the dates are evidence. A reading taken in March 2026 is a fact about
March 2026, and moving it so a chart looks current is the kind of convenience
that ends up quoted in a report. The chart moves; the data does not.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.payment import Payment


@dataclass(frozen=True)
class Anchor:
    """The moment the dashboard treats as the present, and whether it is."""

    moment: datetime
    is_live: bool          # False when the newest measurement predates today
    # The newest month the provider has actually billed, when there are bills.
    # See `last_complete_month` for why a date alone cannot answer that.
    billed_through: date | None = None

    def since(self, days: int) -> datetime:
        return self.moment - timedelta(days=days)

    @property
    def as_of(self):
        return self.moment.date()

    @property
    def month_start(self):
        return self.moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()

    @property
    def last_complete_month(self) -> tuple[date, date]:
        """
        The newest whole month the data covers, as (first day, last day).

        "This month" on a card has to mean a month that happened. Two cards side
        by side describing different periods, one of them empty, is how this
        page reported "Billed This Month 0" beside "Collected This Month 760.2M".

        WHY THE BILLING MONTH DECIDES THIS AND NOT THE ANCHOR DATE
        ---------------------------------------------------------
        The test used to be "is the anchor at or past the last day of its
        month". Against a meter read by hand that is almost never true: this
        provider's newest reading is 12 June, because the reader gets to the
        last street when he gets to it, so June was ruled incomplete and both
        cards fell back to May, a month whose figures were already history.

        June is complete. Three hundred invoices were issued for it. So the
        question is asked of the billing rather than of a date: the newest month
        the provider has actually invoiced is the newest month there is a
        complete picture of.

        `billed_through` is None only for a database with no bills at all, and
        then the old date test is the best available.
        """
        if self.billed_through is not None:
            first = self.billed_through.replace(day=1)
            last = date(first.year, first.month, monthrange(first.year, first.month)[1])
            return first, last

        first = self.moment.replace(day=1).date()
        last = date(first.year, first.month, monthrange(first.year, first.month)[1])
        if self.moment.date() >= last:
            return first, last          # the anchor month is finished

        previous_end = first - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        return previous_start, previous_end


# A dataset is treated as current if its newest row is within this many days of
# today: a load that finished an hour ago should not be labelled historical.
LIVE_WITHIN_DAYS = 2


def customer_anchor(db: Session, customer_id: str) -> datetime:
    """
    The newest reading THIS customer has, or now if they have none.

    Every per-customer analysis window, the recommendation engine's 90 days,
    the alert engine's 30-day comparison, the daily chart, was measured back
    from the wall clock, and the provider's meters are read by hand and lag
    reality by weeks. Against this dataset all of them landed past the end of
    the readings and returned nothing, so a customer with eighteen months of
    history got no recommendations, no alerts, and an empty chart.

    Returns MIDNIGHT AFTER the newest reading, not the reading's own timestamp.
    Windows in this codebase are half-open, `[start, anchor)`, so an anchor
    equal to the newest reading excludes that very reading, which silently
    dropped the most recent month from the alert comparison and made a
    subscriber whose use had nearly doubled look unremarkable.

    Capped at today: a reading stamped in the future is a clock artefact and
    must not push a window past the present.
    """
    newest = (
        db.query(func.max(Consumption.timestamp))
        .filter(Consumption.customer_id == customer_id)
        .scalar()
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    if newest is None:
        return now
    end_of_newest_day = datetime.combine(newest.date(), time.min) + timedelta(days=1)
    return min(end_of_newest_day, now)


def has_intraday(db: Session, customer_id: str) -> bool:
    """
    Whether this customer's readings carry any time-of-day information.

    A meter read once a month by photographing the dial gives one timestamp a
    month, all at the same hour, so an hourly load curve for that customer
    cannot exist. Asking the data rather than assuming means the answer stays
    right if smart meters are fitted later and real hourly rows start arriving.
    """
    hours = (
        db.query(func.count(func.distinct(func.strftime("%H", Consumption.timestamp))))
        .filter(Consumption.customer_id == customer_id)
        .scalar()
        if db.bind and db.bind.dialect.name == "sqlite"
        else db.query(func.count(func.distinct(func.extract("hour", Consumption.timestamp))))
        .filter(Consumption.customer_id == customer_id)
        .scalar()
    )
    return int(hours or 0) > 1


# How many of a customer's newest rows has_daily looks at: thirty days of
# hourly readings. A meter read once a month has far fewer rows than this, so
# all of its readings are seen.
_DENSITY_SAMPLE_ROWS = 24 * 30


def has_daily(db: Session, customer_id: str) -> bool:
    """
    Whether this customer's readings are dense enough to draw a daily chart.

    A meter read once a month produces one point per month. Plotted on a chart
    captioned "Daily Usage (30 days)" that is two points, each holding a whole
    month's consumption, joined by a line, and one subscriber's page showed
    exactly that: a line climbing from 69 to 101 with an x-axis reading "1, 2",
    beside a card announcing an average daily usage of 85.4 kWh for a household
    that uses about 3.4.

    Neither figure was invented. Both came from dividing by the number of ROWS
    when the label promised a division by DAYS.

    The test is the median gap between consecutive reading DAYS, not the row
    count: a customer might have thirty readings spread over three years. One
    day or less means the readings really are daily and the chart means what it
    says.

    The sample is thirty days of hourly rows. It used to be thirty rows, which
    for a meter that reports every hour is a day and a quarter: two distinct
    days, fewer than the three the test needs, so a customer with hourly data
    was treated as read once a month and shown no daily chart at all.
    """
    rows = (
        db.query(Consumption.timestamp)
        .filter(Consumption.customer_id == customer_id)
        .order_by(Consumption.timestamp.desc())
        .limit(_DENSITY_SAMPLE_ROWS)
        .all()
    )
    days = sorted({row[0].date() for row in rows}, reverse=True)
    if len(days) < 3:
        return False
    gaps = sorted((days[i] - days[i + 1]).days for i in range(len(days) - 1))
    return gaps[len(gaps) // 2] <= 1


def anchor(db: Session) -> Anchor:
    """
    How far the platform's picture of the business actually reaches.

    That is the newest METER READING, and payments are deliberately not
    consulted.

    WHY PAYMENTS ARE NOT PART OF THIS
    ---------------------------------
    They were, on the reasoning that money can arrive against an older bill and
    a revenue window anchored before the last receipt would miss it. It did no
    harm while every payment came out of the supplied file: his readings stop on
    30 June and his payments on 10 July, and `last_complete_month` stepped back
    to June from either.

    Then the Pay button started working. One customer settling one bill wrote a
    payment dated today, the anchor jumped to August, the last complete month
    became July, and the Revenue page went back to showing "Billed This Month
    0 LBP" beside "Collected This Month 760.2M": the exact pairing
    `last_complete_month` was written to stop. A single row of somebody's
    activity had redefined what the whole dashboard called "now".

    A payment recorded today is a real event and it belongs in the totals, where
    it appears immediately. It is not evidence that the platform holds data
    about July or August. The readings are what say how far the picture reaches,
    so they alone set the anchor.
    """
    now = datetime.now(UTC).replace(tzinfo=None)

    # The newest month the provider has invoiced. Read here so `Anchor` stays a
    # plain value object with no database of its own.
    newest_bill_due = db.query(func.max(Bill.due_date)).scalar()
    billed_through = newest_bill_due.replace(day=1) if newest_bill_due else None

    newest = db.query(func.max(Consumption.timestamp)).scalar()
    if newest is None:
        # No readings at all. A brand new database, where a payment date is
        # better than nothing and `now` is better than neither.
        newest_payment = db.query(func.max(Payment.date)).scalar()
        if newest_payment is None:
            return Anchor(moment=now, is_live=True, billed_through=billed_through)
        newest = datetime(newest_payment.year, newest_payment.month, newest_payment.day)
    if newest >= now:
        # Data stamped in the future is a clock or timezone artefact, not a
        # measurement. Fall back to now rather than reporting from ahead.
        return Anchor(moment=now, is_live=True, billed_through=billed_through)

    return Anchor(moment=newest, is_live=(now - newest).days <= LIVE_WITHIN_DAYS,
                  billed_through=billed_through)
