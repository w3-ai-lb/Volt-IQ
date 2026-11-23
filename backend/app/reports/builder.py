"""
Report data builders, the "Report Generation" responsibility listed in
Section V-ii of the Software Architecture, and the "Generate reports" admin
use case / "Business reports" output in the SRS (Sections V and VI-iv).

Each builder turns a date range into a ReportData structure: a title, a set of
summary figures, and one table. Rendering to PDF or Excel is handled
separately in render.py, so a new report type never touches the renderers and
a new output format never touches the queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.money import money
from app.ai import forecasting
from app.analytics import owed
from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class ReportData:
    """One report, ready to render in any format."""

    key: str
    title: str
    description: str
    date_from: date
    date_to: date
    # [(label, value)] shown as a summary block above the table.
    summary: list[tuple[str, str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    # Column indexes (0-based) that hold numbers and should be totalled.
    numeric_columns: list[int] = field(default_factory=list)
    # Optional note printed under the table, e.g. explaining an empty result.
    note: str = ""

    @property
    def filename_stem(self) -> str:
        return f"{self.key}-report-{self.date_from}-to-{self.date_to}"


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Inclusive date range -> half-open datetime range."""
    start = datetime.combine(date_from, time.min)
    end = datetime.combine(date_to, time.max)
    return start, end


def _money(value: float) -> str:
    return money(value)


# ---------------------------------------------------------------------------
# 1. Revenue: "Monthly revenue breakdown by region and plan"
# ---------------------------------------------------------------------------
def _revenue(db: Session, date_from: date, date_to: date) -> ReportData:
    rows_raw = (
        db.query(Customer.region, Customer.plan,
                 func.count(Payment.payment_id), func.coalesce(func.sum(Payment.amount), 0.0))
        .join(Payment, Payment.customer_id == Customer.customer_id)
        .filter(Payment.date >= date_from, Payment.date <= date_to)
        .group_by(Customer.region, Customer.plan)
        .order_by(func.sum(Payment.amount).desc())
        .all()
    )

    rows = [
        [region or "Unassigned", plan or "-", int(count), int(round(float(total or 0)))]
        for region, plan, count, total in rows_raw
    ]
    total_revenue = sum(r[3] for r in rows)
    total_payments = sum(r[2] for r in rows)

    outstanding = owed.outstanding_between(db, date_from, date_to)

    return ReportData(
        key="revenue",
        title="Revenue Report",
        description="Monthly revenue breakdown by region and plan",
        date_from=date_from,
        date_to=date_to,
        summary=[
            ("Total revenue collected", _money(total_revenue)),
            ("Payments received", f"{total_payments:,}"),
            ("Average payment", _money(total_revenue / total_payments) if total_payments else _money(0)),
            ("Outstanding in period", _money(outstanding)),
        ],
        columns=["Region", "Plan", "Payments", f"Revenue ({settings.CURRENCY})"],
        rows=rows,
        numeric_columns=[2, 3],
        note="" if rows else "No payments were recorded in this period.",
    )


# ---------------------------------------------------------------------------
# 2. Consumption: "Aggregate consumption patterns and trends"
# ---------------------------------------------------------------------------
def _consumption(db: Session, date_from: date, date_to: date) -> ReportData:
    start, end = _bounds(date_from, date_to)

    raw = (
        db.query(Consumption.timestamp, Consumption.kwh, Consumption.cost, Customer.region)
        .join(Customer, Customer.customer_id == Consumption.customer_id)
        .filter(Consumption.timestamp >= start, Consumption.timestamp <= end)
        .all()
    )

    # Aggregate per calendar month, per region.
    buckets: dict[tuple[int, int, str], dict[str, float]] = {}
    for timestamp, kwh, cost, region in raw:
        key = (timestamp.year, timestamp.month, region or "Unassigned")
        bucket = buckets.setdefault(key, {"kwh": 0.0, "cost": 0.0})
        bucket["kwh"] += float(kwh or 0)
        bucket["cost"] += float(cost or 0)

    rows = [
        [f"{MONTH_NAMES[month - 1]} {year}", region,
         round(values["kwh"], 1), int(round(values["cost"]))]
        for (year, month, region), values in sorted(buckets.items())
    ]

    total_kwh = sum(r[2] for r in rows)
    days = max(1, (date_to - date_from).days + 1)
    active_meters = (
        db.query(func.count(func.distinct(Consumption.customer_id)))
        .filter(Consumption.timestamp >= start, Consumption.timestamp <= end)
        .scalar() or 0
    )

    return ReportData(
        key="consumption",
        title="Consumption Report",
        description="Aggregate consumption patterns and trends",
        date_from=date_from,
        date_to=date_to,
        summary=[
            ("Total consumption", f"{total_kwh:,.1f} kWh"),
            ("Daily average", f"{total_kwh / days:,.1f} kWh"),
            ("Metered customers", f"{int(active_meters):,}"),
            ("Average per customer", f"{total_kwh / active_meters:,.1f} kWh" if active_meters else "0 kWh"),
        ],
        columns=["Month", "Region", "Consumption (kWh)", f"Billed value ({settings.CURRENCY})"],
        rows=rows,
        numeric_columns=[2, 3],
        note="" if rows else "No consumption readings fall in this period.",
    )


# ---------------------------------------------------------------------------
# 3. Customers: "Customer growth, churn, and segmentation"
# ---------------------------------------------------------------------------
def _customers(db: Session, date_from: date, date_to: date) -> ReportData:
    customers = (
        db.query(Customer).filter(Customer.role == "customer")
        .order_by(Customer.customer_id).all()
    )

    usage = dict(
        db.query(Consumption.customer_id, func.coalesce(func.sum(Consumption.kwh), 0.0))
        .filter(Consumption.timestamp >= _bounds(date_from, date_to)[0],
                Consumption.timestamp <= _bounds(date_from, date_to)[1])
        .group_by(Consumption.customer_id).all()
    )

    rows = [
        [c.customer_id, c.name, c.region or "Unassigned", c.plan, c.status,
         round(float(usage.get(c.customer_id, 0.0)), 1), int(round(float(c.balance or 0)))]
        for c in customers
    ]

    # "New in period" is only sayable when the records carry a joining date
    # that means something. This provider's export does not: it is eighteen
    # months of an already connected customer base, and `created_at` on a
    # generated record is the month of that subscriber's FIRST INVOICE: the
    # same month for all three hundred.
    #
    # Counted plainly, the report announced "New in period: 300", i.e. that the
    # provider tripled from nothing to three hundred subscribers in one month.
    # The admin dashboard was corrected to stop making exactly that claim; this
    # document was still making it, in writing, to whoever the report is for.
    #
    # Distinct joining months is the test: one month for everybody means the
    # date is a placeholder, not a record of when anyone joined.
    joining_months = {
        (c.created_at.year, c.created_at.month) for c in customers if c.created_at
    }
    if len(joining_months) < 2:
        new_in_period = None
    else:
        new_in_period = sum(
            1 for c in customers
            if c.created_at and date_from <= c.created_at.date() <= date_to
        )
    by_status: dict[str, int] = {}
    for c in customers:
        by_status[c.status] = by_status.get(c.status, 0) + 1

    return ReportData(
        key="customers",
        title="Customer Report",
        description="Customer growth, churn, and segmentation",
        date_from=date_from,
        date_to=date_to,
        summary=[
            ("Total customers", f"{len(customers):,}"),
            ("New in period",
             f"{new_in_period:,}" if new_in_period is not None
             else "Not recorded, the data carries no joining dates"),
            ("Active", f"{by_status.get('Active', 0):,}"),
            ("Suspended / Inactive",
             f"{by_status.get('Suspended', 0) + by_status.get('Inactive', 0):,}"),
        ],
        columns=["Customer ID", "Name", "Region", "Plan", "Status",
                 "Consumption (kWh)", f"Balance ({settings.CURRENCY})"],
        rows=rows,
        numeric_columns=[5, 6],
        note="" if rows else "No customer records found.",
    )


# ---------------------------------------------------------------------------
# 4. Anomalies: "All detected anomalies and resolutions"
# ---------------------------------------------------------------------------
def _anomalies(db: Session, date_from: date, date_to: date) -> ReportData:
    start, end = _bounds(date_from, date_to)
    records = (
        db.query(Anomaly).filter(Anomaly.detected_at >= start, Anomaly.detected_at <= end)
        .order_by(Anomaly.detected_at.desc()).all()
    )
    names = dict(db.query(Customer.customer_id, Customer.name).all())

    rows = [
        [a.detected_at.date().isoformat() if a.detected_at else "",
         a.customer_id, names.get(a.customer_id, ""), a.type, a.severity, a.value,
         "Resolved" if a.resolved else "Open"]
        for a in records
    ]

    by_severity: dict[str, int] = {}
    for a in records:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

    return ReportData(
        key="anomalies",
        title="Anomaly Report",
        description="All detected anomalies and resolutions",
        date_from=date_from,
        date_to=date_to,
        summary=[
            ("Anomalies detected", f"{len(records):,}"),
            ("Critical", f"{by_severity.get('critical', 0):,}"),
            ("High", f"{by_severity.get('high', 0):,}"),
            ("Open (unresolved)", f"{sum(1 for a in records if not a.resolved):,}"),
        ],
        columns=["Date", "Customer ID", "Name", "Type", "Severity", "Deviation", "Status"],
        rows=rows,
        numeric_columns=[],
        note="" if rows else "No anomalies were detected in this period.",
    )


# ---------------------------------------------------------------------------
# 5. Forecast: "Demand forecast predictions and a backtest diagnostic"
# ---------------------------------------------------------------------------
# The approved limitation, word for word as in the README and the academic
# report. It describes the supplied dataset; kept with the forecasting code,
# which prints it in GET /ai/evaluation as well.
FORECAST_LIMITATION = forecasting.FORECAST_LIMITATION


def _forecast(db: Session, date_from: date, date_to: date) -> ReportData:
    result = forecasting.generate_forecast(db)
    points = result.get("forecastData", [])
    cards = result.get("forecastCards", [])

    rows = [
        [p["label"],
         "" if p["actual"] is None else round(float(p["actual"]), 1),
         round(float(p["predicted"]), 1),
         round(float(p["lower"]), 1),
         round(float(p["upper"]), 1),
         "Actual" if p["actual"] is not None else "Predicted"]
        for p in points
    ]

    # "Not measured" rather than "None%", which is what a null score printed
    # into an f-string produces.
    #
    # Named as the dashboard card names it: a backtest diagnostic, not an
    # accuracy. On a meter read once a month the backtest measures the reading
    # schedule more than the model; the note at the foot of the report says so.
    backtest = forecasting.model_accuracy(db)
    summary = [(
        "Forecast backtest (diagnostic, not validated accuracy)",
        f"{backtest}%" if backtest is not None else "Not enough history to measure",
    )]
    for card in cards:
        # The model's own 90% interval. This line used to read "(84% confidence)"
        # from a constant chosen by model name, in a document sitting beside a
        # measured accuracy on the line above it.
        summary.append((
            f"{card['period']} forecast",
            f"{float(card['kwh']):,.0f} kWh "
            f"(likely {float(card['lower']):,.0f}, {float(card['upper']):,.0f})",
        ))

    return ReportData(
        key="forecast",
        title="Forecast Report",
        description="Demand forecast predictions and a backtest diagnostic",
        date_from=date_from,
        date_to=date_to,
        summary=summary,
        columns=["Period", "Actual (kWh)", "Predicted (kWh)",
                 "Lower bound", "Upper bound", "Type"],
        rows=rows,
        numeric_columns=[],
        note=(
            "Forecasts are system-wide, as specified in Section VII of the Software "
            "Architecture, so they are not limited to the selected date range. "
            "The backtest figure is a diagnostic, not validated accuracy. On the supplied "
            "dataset: " + FORECAST_LIMITATION
        ),
    )


# ---------------------------------------------------------------------------
# 6. Billing: "Bills issued, payments, and outstanding balances"
# ---------------------------------------------------------------------------
def _billing(db: Session, date_from: date, date_to: date) -> ReportData:
    bills = (
        db.query(Bill).filter(Bill.due_date >= date_from, Bill.due_date <= date_to)
        .order_by(Bill.due_date).all()
    )
    names = dict(db.query(Customer.customer_id, Customer.name).all())

    paid_amounts = dict(
        db.query(Payment.bill_id, func.coalesce(func.sum(Payment.amount), 0.0))
        .group_by(Payment.bill_id).all()
    )

    rows = [
        [b.bill_id, b.customer_id, names.get(b.customer_id, ""), b.month,
         b.due_date.isoformat(), int(round(float(b.amount))),
         int(round(float(paid_amounts.get(b.bill_id, 0.0)))), b.status]
        for b in bills
    ]

    issued = sum(float(b.amount) for b in bills)
    collected = sum(r[6] for r in rows)
    by_status: dict[str, int] = {}
    for b in bills:
        by_status[b.status] = by_status.get(b.status, 0) + 1

    return ReportData(
        key="billing",
        title="Billing Report",
        description="Bills issued, payments, and outstanding balances",
        date_from=date_from,
        date_to=date_to,
        summary=[
            ("Bills issued", f"{len(bills):,}"),
            ("Total billed", _money(issued)),
            ("Total collected", _money(collected)),
            ("Collection rate", f"{collected / issued * 100:.1f}%" if issued else "0.0%"),
            ("Paid / Pending / Overdue",
             f"{by_status.get('Paid', 0)} / {by_status.get('Pending', 0)} / {by_status.get('Overdue', 0)}"),
        ],
        columns=["Bill ID", "Customer ID", "Name", "Billing month", "Due date",
                 f"Amount ({settings.CURRENCY})", f"Paid ({settings.CURRENCY})", "Status"],
        rows=rows,
        numeric_columns=[5, 6],
        note="" if rows else "No bills fall due in this period.",
    )


BUILDERS = {
    "revenue": _revenue,
    "consumption": _consumption,
    "customers": _customers,
    "anomalies": _anomalies,
    "forecast": _forecast,
    "billing": _billing,
}

REPORT_TYPES = list(BUILDERS)


def build(db: Session, report_type: str, date_from: date, date_to: date) -> ReportData:
    """Build one report. Raises KeyError for an unknown type."""
    return BUILDERS[report_type](db, date_from, date_to)
