"""Admin analytics, revenue and customer-management schemas."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import CamelModel

# The three tariff plans. Constrained rather than free text: the admin form
# offers exactly these, and the load-profile logic in the pipeline branches on
# them, so a typo like "commercial " would silently be modelled as a household.
PlanName = Literal["Residential", "Commercial", "Industrial"]

# Set by the provider, not chosen freely: Deactivate and Activate are their own
# use cases with their own endpoints, and login refuses the last two.
AccountStatus = Literal["Active", "Inactive", "Suspended"]


class CustomerOut(CamelModel):
    id: str
    name: str
    email: str
    phone: str | None = None
    address: str | None = None
    region: str | None = None
    plan: str
    status: str
    consumption: float
    balance: float
    # False until the customer has registered for portal access with this
    # Customer ID. The admin list shows it so staff can tell who can log in.
    registered: bool = False


class CustomerCreate(BaseModel):
    """
    Payload for the admin "Add Customer" form.

    The five required fields are exactly the inputs the SRS specifies for the
    Customer Management Module (Section VI-i): Customer ID, Full Name, Email
    Address, Phone Number, Address. Region and plan are additional, needed for
    the regional and segment analytics the Proposal asks for.

    Deliberately no password field. The admin creates the customer *record*;
    the customer then registers for portal access with this Customer ID and
    chooses their own password. Setting a shared default here would give every
    admin-created account the same known credentials.
    """

    # Required: this is the provider's account number and the key that links
    # the customer to their meter readings.
    customer_id: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    region: str | None = None
    plan: PlanName = "Residential"


class CustomerUpdate(BaseModel):
    """
    Payload for the admin "Edit Customer" form. Only sent fields change.

    Covers every editable field from the SRS input list, so "update existing
    customer details" is actually possible for all of them.
    """

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    region: str | None = None
    plan: PlanName | None = None
    status: AccountStatus | None = None


class DeleteResult(CamelModel):
    id: str
    deleted: bool
    removed_consumption_rows: int
    removed_bills: int
    removed_payments: int


class RiskCustomerOut(CamelModel):
    """One scored account from the payment-default model."""

    customer_id: str
    name: str
    region: str | None = None
    plan: str | None = None
    score: float
    band: str                       # 'High' | 'Medium' | 'Low' | 'Unknown'
    outstanding: float
    overdue_bills: int
    avg_days_late: float
    days_since_payment: int | None = None
    # Why the model scored it this way: shown in the UI so staff can act on
    # the finding rather than take a number on trust.
    reasons: list[str]


class RiskSummaryOut(CamelModel):
    high: int
    medium: int
    low: int
    unknown: int
    amount_at_risk: float
    # The date the recency signal is counted to: the newest data, not today.
    as_of: date | None = None
    customers: list[RiskCustomerOut]


class RegionalStatOut(CamelModel):
    region: str
    customers: int
    revenue: float
    consumption: float


class TopConsumerOut(CamelModel):
    name: str
    consumption: float
    # None when the previous 30 days hold no reading for this customer, which
    # is common with a meter read once a month. The UI prints a dash; it used
    # to receive 0.0 and print "0.0%", which reads as "no change" rather than
    # "no comparison".
    change: float | None = None


class RevenuePointOut(CamelModel):
    month: str
    revenue: float


class CustomerGrowthOut(CamelModel):
    month: str
    customers: int


class BillingStatusOut(CamelModel):
    status: str
    count: int


class AdminStatsOut(CamelModel):
    total_customers: int
    active_customers: int
    revenue: float
    monthly_consumption: float
    # None when there is not enough history to backtest. The card says so in
    # words rather than printing a 0% that reads as a broken model.
    prediction_accuracy: float | None = None
    revenue_change: float
    # None when the data carries no joining dates, so growth cannot be measured
    # at all. "+0.0%" would claim we looked and nobody joined.
    customers_change: float | None = None
    consumption_change: float
    # The calendar month `monthly_consumption` is for, as YYYY-MM: the newest
    # COMPLETE month, which is not the month of `as_of` unless the data reaches
    # its last day. Printed beside the figure so a May total is not read as
    # June's under an "as of 12 June" heading. None when there is no data.
    consumption_period: str | None = None

    # The day the month-based figures above are measured to. It is the newest
    # measurement in the database, not the wall clock: the supplied dataset
    # ends before today, and a "last 30 days" window run from now would report
    # zero and look like a quiet month rather than the end of a file.
    # `is_live` is False when that day is not today, and the card says so.
    as_of: date | None = None
    is_live: bool = True


class ActivityOut(CamelModel):
    id: str
    text: str
    time: str
    type: str


class PaymentCountPointOut(CamelModel):
    month: str
    count: int


class KpiChangesOut(CamelModel):
    """
    Month-on-month change for each headline figure, as a percentage.

    Every field is optional and null means "no previous month to compare
    against". That case has to be sayable: the Analytics page used to print
    four fixed percentages beside genuinely fetched values, so the figures were
    live and their movement was invented.
    """

    revenue: float | None = None
    consumption: float | None = None
    bills: float | None = None
    payments: float | None = None


class BusinessKpisOut(CamelModel):
    revenue: float
    consumption: float
    bills: int
    payments: int
    top_consumers: list[TopConsumerOut]
    regional_stats: list[RegionalStatOut]
    revenue_trend: list[RevenuePointOut] = []
    payment_trend: list[PaymentCountPointOut] = []
    changes: KpiChangesOut = KpiChangesOut()


class RevenueOverviewOut(CamelModel):
    revenue_trend: list[RevenuePointOut]
    regional_stats: list[RegionalStatOut]
    billing_statuses: list[BillingStatusOut]

    # Money, straight from the bills and payments tables. The currency is
    # settings.CURRENCY: LBP for this provider, and stated on every row of
    # his own data. These are bare numbers; app/core/money.py formats them.
    billed_this_month: float = 0.0
    collected_this_month: float = 0.0
    # The month the two figures above cover, named, and whether that is the
    # month the calendar is in. Without it "This Month" means June to the data
    # and August to the reader.
    period_label: str = ""
    period_is_current: bool = True
    outstanding_total: float = 0.0
    total_revenue: float = 0.0
