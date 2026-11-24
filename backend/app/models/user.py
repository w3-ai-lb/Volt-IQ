"""
Staff sign-in accounts: administrators, office staff and field employees.

WHY THIS TABLE EXISTS (Stage 2, "Users")
----------------------------------------
Until Stage 2 every login lived in `customers`, so a field employee or an
administrator was stored as a "customer" with a special role. That mixed two
different things in one table, and every query about customers had to
remember to filter them out.

Now:

    customers  -> the provider's customers. A customer who claimed portal
                  access still signs in with the password on their own row
                  (the registration-code flow depends on it).
    users      -> everybody who WORKS for the provider and signs in.

Sign-in (`/auth/login`) looks in `users` first and then in `customers`; the
token says which table it came from (`kind` claim, see app/core/security.py).

THE SAME ATTRIBUTE NAMES AS Customer, ON PURPOSE
-----------------------------------------------
About ninety places in the routers read `current_user.customer_id`,
`.role`, `.name`, `.email`, `.theme`... A User answers to the same names
(`customer_id` is an alias of `user_id`), so the shared endpoints (profile,
change password, admin analytics, CRM) work for both kinds of account
without being rewritten.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Roles a User may have. Customers are never Users.
USER_ROLES = frozenset({"admin", "staff", "field"})


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # 'admin' | 'staff' | 'field'
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")
    # 'Active' | 'Inactive' | 'Suspended'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")

    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(60))

    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="light")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    # Raised on every password change; tokens carrying an older value are refused.
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # --- compatibility with code written for Customer ---------------------
    kind = "user"
    plan = "Staff"

    @property
    def customer_id(self) -> str:
        """Alias of user_id, so shared code that reads `customer_id` keeps working."""
        return self.user_id

    @property
    def is_claimed(self) -> bool:
        return bool(self.password_hash)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.user_id} {self.email} {self.role}>"
