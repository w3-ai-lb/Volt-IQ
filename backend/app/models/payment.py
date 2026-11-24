"""
Entity 4, Payments.

Per Section VII of the Software Architecture: "each payment is linked to a
specific bill", hence the bill_id foreign key alongside customer_id.
"""

from datetime import date as date_type

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    # Business key, e.g. "PAY-7841"
    payment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    bill_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("bills.bill_id"))

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)

    # 'Completed' | 'Partial' | 'Failed'
    status: Mapped[str] = mapped_column(String(20), default="Completed", nullable=False)

    # Stage 2 (linked billing): the matching CRM invoice payment, so one payment
    # is never counted twice. See app/core/billing_link.py.
    invoice_payment_id: Mapped[str | None] = mapped_column(String(20), index=True)

    customer = relationship("Customer", back_populates="payments")
    bill = relationship("Bill", back_populates="payments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.payment_id} {self.amount}>"
