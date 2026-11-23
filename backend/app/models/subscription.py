"""
The demand side: who buys electricity, on what terms, through which meter,
and what the meter said each month.

A NOTE ON WHY THESE ARE NOT THE EXISTING `customers` AND `consumption`
---------------------------------------------------------------------
They look similar and they are not the same thing.

`consumption` holds a kWh amount for a moment in time. A meter reading holds
the number on the dial, which only ever goes up. Consumption is the DIFFERENCE
between two readings, so loading readings into the consumption table would
draw a chart that climbs forever and call it usage.

`customers` is the authentication principal: it carries the password hash and
the role, because somebody signs in with it. A subscriber is a record the
provider holds, and most subscribers never sign in to anything. Keeping them
apart means a subscriber can exist without an account, which is the normal
case, and an account can be attached later without reshaping the data.
"""

from datetime import date as date_type

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Subscriber(Base):
    """A household or business buying supply from the ishtirak."""

    __tablename__ = "subscribers"

    subscriber_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    zone_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("zones.zone_id", ondelete="SET NULL"), index=True
    )
    subscriber_type: Mapped[str | None] = mapped_column(String(20))  # residential | commercial | industrial

    # Set once somebody registers for online access. Null for the ordinary
    # case, which is a subscriber the provider bills and who never signs in.
    customer_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="SET NULL")
    )

    subscriptions = relationship(
        "Subscription", back_populates="subscriber", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscriber {self.subscriber_id} {self.zone_id} {self.subscriber_type}>"


class Subscription(Base):
    """
    The contract: which generator feeds this subscriber, at what ampere limit.

    `ampere_capacity` is the contracted ceiling, and it is what makes the
    over-draw rule possible: a subscriber drawing more than they pay for is
    both a billing question and a loss cause, because the extra current heats
    the cable for everybody on the feeder.
    """

    __tablename__ = "subscriptions"

    subscription_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    subscriber_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscribers.subscriber_id", ondelete="CASCADE"), nullable=False
    )
    generator_id: Mapped[str | None] = mapped_column(String(10), index=True)
    zone_id: Mapped[str | None] = mapped_column(String(10), index=True)

    ampere_capacity: Mapped[float | None] = mapped_column(Float)
    phase_type: Mapped[str | None] = mapped_column(String(20))     # single_phase | three_phase
    billing_model: Mapped[str | None] = mapped_column(String(20))  # metered | flat

    # The status recorded on the contract. Note that this is NOT the field the
    # disconnected-but-consuming rule should read: see MeterReading below.
    status: Mapped[str] = mapped_column(String(20), default="active")

    subscriber = relationship("Subscriber", back_populates="subscriptions")
    meter = relationship(
        "Meter", back_populates="subscription", uselist=False, cascade="all, delete-orphan"
    )
    readings = relationship(
        "MeterReading", back_populates="subscription", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscription {self.subscription_id} {self.ampere_capacity}A {self.status}>"


class Meter(Base):
    """
    The physical meter.

    `digit_count` and `multiplier` are not trivia. A five-digit meter rolls
    over from 99999 to 00000, and a reading lower than the previous one is a
    rollover rather than a reversed meter whenever the difference is about one
    full turn of the dial. Reading the raw drop as theft, without checking the
    digit count, is one of the easiest false accusations to make.
    """

    __tablename__ = "meters"

    meter_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"), nullable=False
    )

    serial_number: Mapped[str | None] = mapped_column(String(40))
    meter_type: Mapped[str | None] = mapped_column(String(20))     # digital | mechanical
    digit_count: Mapped[int | None] = mapped_column(Integer)
    multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    initial_reading: Mapped[float | None] = mapped_column(Float)

    subscription = relationship("Subscription", back_populates="meter")
    readings = relationship("MeterReading", back_populates="meter")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Meter {self.meter_id} {self.meter_type} {self.digit_count} digits>"


class MeterReading(Base):
    """
    What the dial said, when it was read, and how much that reading is trusted.

    THREE FIELDS THAT LOOK LIKE METADATA AND ARE NOT
    ------------------------------------------------
    `ocr_confidence`: the reading was captured by photographing the meter and
    running OCR. A misread 4 as 1 is the briefing's Type 3 loss, and it is
    invisible unless the confidence travels with the number.

    `reading_date` versus `billing_period`: the generator's month runs 1 to 31.
    The meters are read over about ten days somewhere inside it. Comparing the
    two totals directly compares two different windows, and the error is worth
    several percent with nothing actually wrong. Keeping the actual date is
    what makes that correctable instead of merely regrettable.

    `subscription_status`: the status AT THE MOMENT OF READING, which is the
    field the disconnected-but-consuming rule must use. The contract table
    holds today's status, so a subscriber cut off in March and reconnected in
    June reads as active there and hides the very thing being looked for.
    """

    __tablename__ = "meter_readings"

    reading_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    meter_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscriptions.subscription_id", ondelete="CASCADE"), nullable=False
    )

    billing_period: Mapped[date_type] = mapped_column(Date, nullable=False)
    reading_value: Mapped[float] = mapped_column(Float, nullable=False)

    capture_method: Mapped[str | None] = mapped_column(String(20))   # ocr | manual
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    was_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_status: Mapped[str | None] = mapped_column(String(20))
    reading_date: Mapped[date_type | None] = mapped_column(Date)

    meter = relationship("Meter", back_populates="readings")
    subscription = relationship("Subscription", back_populates="readings")

    __table_args__ = (
        Index("ix_reading_subscription_period", "subscription_id", "billing_period"),
        Index("ix_reading_period", "billing_period"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MeterReading {self.reading_id} {self.billing_period} {self.reading_value}>"
