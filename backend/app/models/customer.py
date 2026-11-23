"""
Entity 1, Customers.

Doubles as the authentication principal: it carries the password hash and
the role, so /auth/login and /auth/register work against this single table.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# The interface languages the frontend ships a catalogue for, kept here beside
# the column that stores them so the permitted values and the storage cannot
# drift apart. Mirrors LANGUAGES in src/i18n/t.ts.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "ar", "es", "fr", "de", "zh", "ja"})

DEFAULT_LANGUAGE = "en"


class Customer(Base):
    __tablename__ = "customers"

    # Human-readable business key, e.g. "CUST-0001"
    customer_id: Mapped[str] = mapped_column(String(20), primary_key=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Empty for a record loaded from the provider's data that nobody has
    # registered for yet. bcrypt cannot verify against an empty hash, so such
    # an account can never be signed into until registration sets a password.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Role-Based Access Control: 'customer' | 'admin'
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)

    # Per-user UI preference: 'light' | 'dark'. Stored server-side so the
    # choice follows the user to any browser or device.
    theme: Mapped[str] = mapped_column(String(10), default="light", nullable=False)

    # Interface language, for the same reason and in the same way as the theme.
    # It belongs to the account, not to the browser: two people who share a
    # computer each keep their own, and a newly registered account starts from
    # the default rather than inheriting whatever the last person chose.
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)

    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(60), index=True)

    # Present because the CRM project's `subscribers` table carries gps_lat and
    # gps_lng, and the supervisor asked for the two record shapes to match.
    #
    # A WARNING THAT BELONGS NEXT TO THE COLUMN, NOT IN A COMMIT MESSAGE: in the
    # CRM seed these coordinates are scattered across Mount Lebanon without
    # regard to which zone the subscriber is in, two neighbours on the same
    # feeder can sit 20 km apart. They are placeholders for a survey nobody has
    # done. Nothing may compute a distance, a route or a cable length from them.
    # The loss model's `avg_distance_m` comes from the supervisor's own zone
    # file and must keep coming from there.
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lng: Mapped[float | None] = mapped_column(Float)

    # 'Residential' | 'Commercial'
    plan: Mapped[str] = mapped_column(String(30), default="Residential", nullable=False)
    # 'Active' | 'Suspended' | 'Inactive'
    status: Mapped[str] = mapped_column(String(20), default="Active", nullable=False)

    # One-time registration code, see app/core/registration_codes.py: a bcrypt
    # hash of the code and the moment it stops working. Both stay empty until
    # the provider issues a code, and are cleared again once it has been used.
    registration_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Raised by one every time the password changes (or portal access is
    # revoked). Every sign-in token carries the value it was issued with, and a
    # token whose value is out of date is refused, which is what signs out the
    # other devices. See app/core/deps.py.
    session_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Denormalised rollups kept in sync by the pipeline: they let the
    # admin customer table render without an expensive join per row.
    consumption: Mapped[float] = mapped_column(Float, default=0.0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    @property
    def is_claimed(self) -> bool:
        """True once someone has registered for online access to this account."""
        return bool(self.password_hash)

    # One customer has many … (Section VII relationships)
    consumption_records = relationship(
        "Consumption", back_populates="customer", cascade="all, delete-orphan"
    )
    bills = relationship("Bill", back_populates="customer", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="customer", cascade="all, delete-orphan")
    recommendations = relationship(
        "Recommendation", back_populates="customer", cascade="all, delete-orphan"
    )
    conversations = relationship(
        "ChatConversation", back_populates="customer", cascade="all, delete-orphan"
    )
    alerts = relationship("Alert", back_populates="customer", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="customer", cascade="all, delete-orphan")

    # Which alert categories this customer wants. One row at most; absent means
    # every category is on, which is the default for an account that has never
    # opened Settings.
    notification_preference = relationship(
        "NotificationPreference",
        back_populates="customer",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Customer {self.customer_id} {self.email}>"
