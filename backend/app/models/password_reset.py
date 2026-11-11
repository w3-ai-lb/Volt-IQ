"""
Password reset tokens, supports the "Password Reset" requirement in
Section III-ii of the SRS.

Stored as a SHA-256 hash, never in the clear. A reset token grants control of
an account, so a leaked database table must not hand out working tokens; the
same reasoning that applies to passwords applies here.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # SHA-256 of the token that was issued. The plain value is shown once and
    # never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    customer = relationship("Customer")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PasswordResetToken {self.customer_id} used={self.used}>"
