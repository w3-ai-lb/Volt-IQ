"""
Composite dashboard payloads.

These two endpoints each return one aggregated object so the dashboards render
in a single round-trip instead of a request waterfall.
"""

from app.schemas.ai import ForecastPoint
from app.schemas.analytics import (
    ActivityOut,
    AdminStatsOut,
    CustomerGrowthOut,
    RevenuePointOut,
    TopConsumerOut,
)
from app.schemas.billing import AlertOut, BillOut, PaymentOut, RecommendationOut
from app.schemas.common import CamelModel
from app.schemas.consumption import MonthlyConsumptionOut


class CustomerDashboardOut(CamelModel):
    """
    Shape consumed by src/pages/customer/CustomerDashboard.tsx.

    NOTE: `monthly_consumption` and `current_bill` are deliberately NOT
    optional. The dashboard reads `data.monthlyConsumption.kwh` and
    `data.currentBill.amount` with no null guard, so returning null for an
    account with no history (a freshly registered user, or the admin account)
    crashes the page. The router always supplies a zero-value object instead.
    """

    monthly_consumption: MonthlyConsumptionOut
    current_bill: BillOut
    outstanding_balance: float

    # `energy_saving_score` IS optional, unlike the two fields above, and the
    # dashboard guards it. Null means the account has no usable history, so
    # there is no score to show. It must not be defaulted to a number: a
    # fabricated score reads exactly like a measured one.
    #
    # `basis` is "year" (compared with the same 30 days last year) or "month"
    # (compared with the previous 30 days), so the card can state what the
    # score is measured against. `change_pct` is the underlying change in
    # average daily usage, positive meaning the customer used more.
    energy_saving_score: int | None = None
    energy_saving_basis: str | None = None
    energy_saving_change_pct: float | None = None

    consumption_trend: list[MonthlyConsumptionOut]
    monthly_bills: list[BillOut]
    payment_history: list[PaymentOut]
    recent_recommendations: list[RecommendationOut]
    recent_alerts: list[AlertOut]


class CustomerBaseOut(CamelModel):
    month: str
    billed: int
    settled: int


class AdminDashboardOut(CamelModel):
    """Shape consumed by src/pages/admin/AdminDashboard.tsx."""

    stats: AdminStatsOut
    revenue_trend: list[RevenuePointOut]
    customer_growth: list[CustomerGrowthOut]
    # The chart that replaced the empty growth card: the size of the
    # customer base month by month, measured from the invoices actually
    # issued rather than from a joining date the provider never recorded.
    customer_base: list[CustomerBaseOut]
    forecast_data: list[ForecastPoint]
    consumption_trend: list[MonthlyConsumptionOut]
    top_consumers: list[TopConsumerOut]
    recent_activities: list[ActivityOut]
