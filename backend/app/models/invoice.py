"""
Money: the monthly tariff, the invoice it produces, and the payment against it.

WHY THE EXISTING `bills` TABLE WAS NOT REUSED
---------------------------------------------
`bills` holds an amount and a status, which is all a customer portal needs to
show. An ishtirak invoice has to hold more than that to be checkable: the
units it was calculated from, the tariff row that set the rate, and the split
between the fixed subscription charge and the variable per-kWh charge.

That split is not bookkeeping detail. The fixed charge is paid whether or not
a single kWh flows, so an invoice total on its own cannot be turned back into
energy. The loss calculation compares kWh with kWh, and `units_consumed` is
the only column here that belongs in it.
"""

from datetime import date as date_type

from sqlalchemy import Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tariff(Base):
    """
    The rate for one month.

    Lebanon's Ministry of Energy and Water publishes a per-kWh rate monthly,
    and it moves with the diesel price rather than staying still: across the
    eighteen months in this dataset the base rate travels between roughly
    27,000 and 39,000 LBP per kWh. A single TARIFF constant in configuration,
    which is what the platform had, cannot represent that, and any revenue
    comparison made with one is comparing months at the wrong price.

    `rate_per_kwh_highland` is the higher rate for zones above 700 m, so which
    rate applies is a property of the zone, not of the customer.

    `diesel_price_per_20l` and `usd_exchange_rate` are stored beside the rate
    because they are what explains a change in it, and the owner's first
    question about any month is always why.
    """

    __tablename__ = "tariffs"

    tariff_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    effective_month: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    rate_per_kwh_base: Mapped[float] = mapped_column(Float, nullable=False)
    rate_per_kwh_highland: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="LBP")

    diesel_price_per_20l: Mapped[float | None] = mapped_column(Float)
    usd_exchange_rate: Mapped[float | None] = mapped_column(Float)

    invoices = relationship("Invoice", back_populates="tariff")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tariff {self.tariff_id} {self.rate_per_kwh_base} {self.currency}/kWh>"


class Invoice(Base):
    """One monthly bill issued to one subscription."""

    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"), nullable=False
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscribers.subscriber_id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[str | None] = mapped_column(String(10), index=True)

    billing_period: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    # The BILLED side of the loss equation. Everything else on this row is money.
    units_consumed: Mapped[float] = mapped_column(Float, default=0.0)

    tariff_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("tariffs.tariff_id", ondelete="SET NULL")
    )
    rate_applied: Mapped[float | None] = mapped_column(Float)

    fixed_charge: Mapped[float] = mapped_column(Float, default=0.0)
    variable_charge: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="LBP")

    tariff = relationship("Tariff", back_populates="invoices")
    invoice_payments = relationship(
        "InvoicePayment", back_populates="invoice", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_invoice_zone_period", "zone_id", "billing_period"),
        Index("ix_invoice_subscriber_period", "subscriber_id", "billing_period"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Invoice {self.invoice_id} {self.units_consumed}kWh {self.total_amount}{self.currency}>"


class InvoicePayment(Base):
    """
    A payment against an ishtirak invoice.

    Named apart from the platform's existing `payments` table rather than
    merged into it: that one hangs off `customers` and a bill, this one hangs
    off a subscriber and an invoice, and the two id spaces are unrelated.
    Merging them would mean a foreign key that points at one of two tables
    depending on where the row came from, which is the kind of thing that
    works until somebody writes a join.

    `collected_by` is the employee who took the money. It is here because
    collector fraud is a real pattern in this business: cash taken, receipt
    given, invoice never marked paid. It cannot be looked for without this.
    """

    __tablename__ = "invoice_payments"

    payment_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    invoice_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscribers.subscriber_id", ondelete="CASCADE"), nullable=False
    )

    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="LBP")
    payment_method: Mapped[str | None] = mapped_column(String(30))   # cash | omt | whish
    payment_date: Mapped[date_type | None] = mapped_column(Date, index=True)
    collected_by: Mapped[str | None] = mapped_column(String(20), index=True)

    invoice = relationship("Invoice", back_populates="invoice_payments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InvoicePayment {self.payment_id} {self.amount}{self.currency} {self.payment_method}>"
