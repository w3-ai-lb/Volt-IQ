"""
Consumption router, monthly / daily / hourly aggregations.

Every series is derived from the `consumption` table by aggregation, which is
why loading the supervisor's dataset into that one table makes all three
charts light up at once.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import asof
from app.config import settings
from app.core.money import money
from app.core.deps import get_current_user, require_admin
from app.database import get_db
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.network import GeneratorTelemetry
from app.schemas.consumption import (
    DailyConsumptionOut,
    HeatmapOut,
    HourlyConsumptionOut,
    MonthlyConsumptionOut,
)

router = APIRouter(prefix="/consumption", tags=["Consumption"])

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Monday first, matching datetime.weekday().
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def monthly_series(db: Session, customer_id: str, months: int = 12) -> list[dict]:
    """
    The last N calendar months of kWh and cost for one customer, ending with
    the month of their newest reading.

    COUNTED FROM THE NEWEST READING, NOT FROM TODAY
    -----------------------------------------------
    The window used to run back from the wall clock. The provider's export
    ends in June 2026, so in October 2026 "the last 12 months" held nine months
    of readings, and one fewer for every month that passed: the dashboard
    chart, the Consumption page and the PDF statement all shrank on their own.
    The anchor is the one the daily chart and the analyses already use
    (asof.customer_anchor): midnight after this customer's newest reading,
    capped at today, so with live data nothing changes.

    `period` is the month as YYYY-MM, because `month` alone ("Jan") cannot tell
    two Januaries apart once a range runs past twelve months.
    """
    anchor = asof.customer_anchor(db, customer_id)
    since = (anchor - timedelta(days=months * 31)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    rows = (
        db.query(Consumption.timestamp, Consumption.kwh, Consumption.cost)
        .filter(
            Consumption.customer_id == customer_id,
            Consumption.timestamp >= since,
            Consumption.timestamp < anchor,
        )
        .all()
    )

    buckets: dict[tuple[int, int], dict[str, float]] = {}
    for timestamp, kwh, cost in rows:
        key = (timestamp.year, timestamp.month)
        bucket = buckets.setdefault(key, {"kwh": 0.0, "cost": 0.0})
        bucket["kwh"] += float(kwh or 0)
        bucket["cost"] += float(cost or 0)

    ordered = sorted(buckets.items())[-months:]
    return [
        {
            "month": MONTH_NAMES[month - 1],
            "period": f"{year:04d}-{month:02d}",
            "kwh": round(values["kwh"], 1),
            "cost": round(values["cost"], 2),
        }
        for (year, month), values in ordered
    ]


@router.get("/monthly", response_model=list[MonthlyConsumptionOut])
def get_monthly(
    months: int = Query(12, ge=1, le=24, description="How many calendar months to return"),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Monthly totals for the last `months` calendar months.

    The range is a parameter so the Consumption page's range selector has
    something real to change. It used to be fixed at 12 while the page offered
    a year picker that altered nothing.
    """
    return monthly_series(db, current_user.customer_id, months=months)


@router.get("/daily", response_model=list[DailyConsumptionOut])
def get_daily(
    days: int = Query(30, ge=1, le=365, description="How many days back to include"),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Daily totals for the last `days` days OF THIS CUSTOMER'S DATA.

    Anchored on their newest reading rather than on today: the provider's
    meters are read by hand and lag by weeks, so a wall-clock window returned
    an empty chart for accounts with eighteen months of history.

    RETURNS NOTHING WHEN THE METER IS NOT READ DAILY
    ------------------------------------------------
    Same decision as `get_hourly` below, for the same reason. This used to
    return one row per reading regardless of how far apart the readings were,
    so a hand-read meter produced a two-point "Daily Usage (30 days)" chart in
    which each point was a whole month's consumption. Nothing on the page said
    so, and the card above it divided the same rows by their own count and
    called the answer an average daily usage, which came out twenty-five times
    the truth.

    A chart cannot be more granular than the meter behind it.
    """
    if not asof.has_daily(db, current_user.customer_id):
        return []

    now = asof.customer_anchor(db, current_user.customer_id)
    since = now - timedelta(days=days)

    rows = (
        db.query(Consumption.timestamp, Consumption.kwh)
        .filter(
            Consumption.customer_id == current_user.customer_id,
            Consumption.timestamp >= since,
        )
        .all()
    )

    buckets: dict[str, float] = {}
    for timestamp, kwh in rows:
        buckets[timestamp.date().isoformat()] = buckets.get(
            timestamp.date().isoformat(), 0.0
        ) + float(kwh or 0)

    return [
        {"day": index, "kwh": round(buckets[key], 1)}
        for index, key in enumerate(sorted(buckets), start=1)
    ]


@router.get("/hourly", response_model=list[HourlyConsumptionOut])
def get_hourly(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Average 24-hour load profile over the last 14 days of this customer's data.

    Averaging rather than taking a single day smooths out one-off events and
    produces the characteristic morning/evening double peak.

    RETURNS NOTHING WHEN THE METER CANNOT PRODUCE IT
    -----------------------------------------------
    A meter read once a month by photographing the dial gives one timestamp a
    month, all stamped at the same hour. Bucketing those by hour draws a single
    spike at midnight and twenty-three empty hours, which looks like a customer
    who uses all their electricity at 00:00. The data is asked whether it has
    any time-of-day information at all, and if it does not, this returns an
    empty list and the page says why.

    The only genuine hourly record in this system is measured at the generator,
    and it is on the admin heatmap, where it belongs.
    """
    if not asof.has_intraday(db, current_user.customer_id):
        return []

    now = asof.customer_anchor(db, current_user.customer_id)
    since = now - timedelta(days=14)

    rows = (
        db.query(
            func.extract("hour", Consumption.timestamp).label("hour"),
            func.avg(Consumption.kwh).label("avg_kwh"),
        )
        .filter(
            Consumption.customer_id == current_user.customer_id,
            Consumption.timestamp >= since,
        )
        .group_by("hour")
        .all()
    )

    by_hour = {int(hour): float(avg or 0) for hour, avg in rows}
    return [
        {"hour": f"{hour}:00", "kwh": round(by_hour.get(hour, 0.0), 2)}
        for hour in range(24)
    ]


@router.get("/heatmap", response_model=HeatmapOut)
def get_heatmap(
    days: int = 28,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """
    System-wide load by weekday and hour, for the admin dashboard heatmap.

    Four weeks by default, so each of the seven weekday buckets is an average
    over four samples rather than one, enough for the weekday/weekend split to
    show through without a single unusual day dominating a row.

    This replaces a hardcoded sine wave that the dashboard used to draw. It
    looked like a plausible daily load curve, which is precisely the problem:
    it was the same picture whatever the data said.

    READ FROM THE GENERATORS, NOT FROM THE METERS
    --------------------------------------------
    It used to read the `consumption` table, and against this provider's data
    that grid came out completely blank. His meters are read once a month, so a
    subscriber has eighteen timestamps in eighteen months and there is no hour
    of the day to bucket them into. A blank 7x24 grid on the dashboard reads as
    a broken feature rather than as an honest absence.

    But the measurement does exist, one level up: `generator_telemetry` holds
    48,013 hourly rows with active power on every one of them, which is what
    system-wide load by hour actually means. The generators are where load is
    metered continuously; the subscriber meters are read by hand with a camera.
    So the question the card asks is answered from the place that can answer it.

    Averaging kW over a whole hour gives the kWh delivered in that hour, so the
    unit on the card is unchanged and still correct.
    """
    days = max(7, min(days, 180))

    # Anchored to the newest telemetry rather than to the wall clock: a
    # historical export legitimately stops before today, and a window measured
    # back from now would land past the end of it and return nothing.
    newest = db.query(func.max(GeneratorTelemetry.timestamp)).scalar()
    if newest is None:
        return {
            "days": WEEKDAY_NAMES,
            "hours": [f"{hour}:00" for hour in range(24)],
            "grid": [[0.0] * 24 for _ in range(7)],
            "max_kwh": 0.0,
            "window_days": days,
        }
    since = newest - timedelta(days=days)

    rows = (
        db.query(GeneratorTelemetry.timestamp, GeneratorTelemetry.active_power_kw)
        .filter(GeneratorTelemetry.timestamp >= since)
        .all()
    )

    # Sum per (weekday, hour) across every generator, then divide by how many
    # distinct dates fell in each weekday bucket: a plain average over rows
    # would let a weekday with more generators reporting look busier than one
    # with fewer.
    totals: dict[tuple[int, int], float] = {}
    dates_seen: dict[int, set] = {}
    for timestamp, kwh in rows:
        weekday = timestamp.weekday()      # Monday = 0
        key = (weekday, timestamp.hour)
        totals[key] = totals.get(key, 0.0) + float(kwh or 0)
        dates_seen.setdefault(weekday, set()).add(timestamp.date())

    grid: list[list[float]] = []
    for weekday in range(7):
        occurrences = max(1, len(dates_seen.get(weekday, ())))
        grid.append(
            [round(totals.get((weekday, hour), 0.0) / occurrences, 2) for hour in range(24)]
        )

    flat = [value for row in grid for value in row]
    return {
        "days": WEEKDAY_NAMES,
        "hours": [f"{hour}:00" for hour in range(24)],
        "grid": grid,
        "max_kwh": round(max(flat), 2) if flat else 0.0,
        "window_days": days,
    }


@router.get("/export")
def export_consumption(
    months: int = Query(12, ge=1, le=24, description="How many calendar months to include"),
    format: str = Query("pdf", pattern="^(pdf|excel)$"),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    The customer's own consumption statement, as a PDF or a spreadsheet.

    WHY THIS EXISTS
    ---------------
    The Export button on the Consumption page used to raise a toast saying
    "Your PDF report is being generated" and then generate nothing. There was
    no endpoint behind it. The existing /reports endpoints could not be used
    either: they are admin-only and system-wide, so pointing the customer page
    at one would have handed every customer the whole provider's figures.

    This builds the same ReportData structure the admin reports use, over one
    customer's rows only, and hands it to the same renderers.
    """
    from app.reports import render
    from app.reports.builder import ReportData

    series = monthly_series(db, current_user.customer_id, months=months)
    # The period the statement covers is the period its rows cover: from the
    # first day of the first month listed to the customer's newest reading.
    # It used to be "the last N x 31 days up to today", which printed dates no
    # row of the statement came from. The anchor is the midnight after the
    # newest reading, or the present moment when that reading is from today
    # (asof.customer_anchor); one microsecond earlier is the reading's own day
    # in both cases.
    anchor = asof.customer_anchor(db, current_user.customer_id)
    newest_day = (anchor - timedelta(microseconds=1)).date() if series else anchor.date()
    first_day = date.fromisoformat(series[0]["period"] + "-01") if series else newest_day

    total_kwh = round(sum(point["kwh"] for point in series), 1)
    total_cost = round(sum(point["cost"] for point in series), 2)
    peak = max(series, key=lambda point: point["kwh"], default=None)

    report = ReportData(
        key=f"consumption-{current_user.customer_id}",
        title="Consumption Statement",
        description=f"Monthly electricity consumption for {current_user.name} ({current_user.customer_id}).",
        date_from=first_day,
        date_to=newest_day,
        summary=[
            ("Account", f"{current_user.name} ({current_user.customer_id})"),
            ("Tariff", current_user.plan),
            ("Months included", str(len(series))),
            ("Total consumption", f"{total_kwh:,.1f} kWh"),
            # Was f"{total_cost:,.2f}" with no unit at all, so a customer's own
            # statement showed "134,982,523.00" and left them to guess what it
            # was denominated in, beside a kWh column that says its unit.
            ("Total cost", money(total_cost)),
            ("Peak month", f"{peak['month']} ({peak['kwh']:,.1f} kWh)" if peak else "No readings"),
        ],
        columns=["Month", "Consumption (kWh)", f"Cost ({settings.CURRENCY})"],
        # Cost rounded to whole pounds: LBP has no circulating subunit, and the
        # shared cell formatter gives floats two decimals.
        rows=[[point["month"], point["kwh"], int(round(point["cost"]))] for point in series],
        numeric_columns=[1, 2],
        note="" if series else "No readings have been recorded for this account yet.",
    )

    payload = render.RENDERERS[format](report)
    filename = f"consumption-{current_user.customer_id}.{render.EXTENSIONS[format]}"
    return Response(
        content=payload,
        media_type=render.MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
