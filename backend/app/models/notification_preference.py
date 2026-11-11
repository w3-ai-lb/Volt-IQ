"""
Entity 11, Notification Preferences: which alerts a customer wants to receive.

WHY A SEPARATE TABLE AND NOT FOUR COLUMNS ON `customers`
--------------------------------------------------------
The project creates its schema with `Base.metadata.create_all`, which adds
missing tables but never alters existing ones. Four new columns on `customers`
would therefore appear on a fresh database and be silently absent on one that
already exists, and every read would fail on the deployed copy. A new table is
created on next start on both.

It is also the more honest shape: preferences are a separate concern from the
account record, and one row per customer keyed by customer_id says so.

WHY THE DEFAULT IS "ON"
-----------------------
A customer who has never opened Settings should receive their alerts. Absence
of a row means all four are on, which is why `for_customer` returns defaults
rather than creating a row on first read: writing to the database on a GET
would turn a page view into a write on every dashboard load.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    customer_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Each flag suppresses one signal of the alert engine, named for what the
    # customer sees rather than for the internal alert type.
    high_usage: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bill_reminders: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    anomalies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    savings_milestones: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customer = relationship("Customer", back_populates="notification_preference")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotificationPreference {self.customer_id}>"


# Maps a preference field to the alert engine's own `type` value. Kept here, next
# to the columns, so adding a signal to the engine and forgetting the preference
# is a one-file discrepancy rather than a search across the codebase.
PREFERENCE_FOR_ALERT_TYPE = {
    "high-usage": "high_usage",
    "payment": "bill_reminders",
    "anomaly": "anomalies",
    "low-usage": "savings_milestones",
}

DEFAULTS = {
    "high_usage": True,
    "bill_reminders": True,
    "anomalies": True,
    "savings_milestones": True,
}
