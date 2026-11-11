"""Entity 3: Bills."""

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bill(Base):
    __tablename__ = "bills"

    # Business key, e.g. "BILL-2026-006"
    bill_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    month: Mapped[str] = mapped_column(String(20), nullable=False)   # "Jun 2026"
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 'Paid' | 'Pending' | 'Overdue'
    status: Mapped[str] = mapped_column(String(20), default="Pending", nullable=False)

    customer = relationship("Customer", back_populates="bills")
    payments = relationship("Payment", back_populates="bill")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Bill {self.bill_id} {self.amount} {self.status}>"
