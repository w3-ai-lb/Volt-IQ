"""
Supporting entity, Alerts.

Not one of the seven entities listed in Section VII of the Software
Architecture, but the alert engine is a required deliverable in the Proposal
("Personalized recommendation and alert engine") and the frontend has a
working Alerts page. Storing alerts is therefore necessary; recommend adding
this table to the ERD in the next revision of the documentation.
"""

from datetime import date as date_type

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # 'high-usage' | 'low-usage' | 'payment' | 'anomaly'
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # 'info' | 'warning' | 'error' | 'success'
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    customer = relationship("Customer", back_populates="alerts")
