"""
Entity 2, Electricity Consumption.

The heart of the platform. Every consumption chart (hourly / daily / monthly)
is an aggregation over this table, and both AI models, demand forecasting
and anomaly detection, are trained on it.

This is the table the supervisor's dataset loads into.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Consumption(Base):
    __tablename__ = "consumption"

    consumption_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kwh: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    customer = relationship("Customer", back_populates="consumption_records")

    # Composite index: every query filters by customer then orders by time.
    __table_args__ = (
        Index("ix_consumption_customer_time", "customer_id", "timestamp"),
        Index("ix_consumption_time", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Consumption {self.customer_id} {self.timestamp} {self.kwh}kWh>"
