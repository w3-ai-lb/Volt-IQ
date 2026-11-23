"""
Supporting entity, Anomalies.

Persists the output of the anomaly-detection model so the admin dashboard can
list findings without re-running inference on every request. Like Alerts, this
is a required capability in both the Proposal and Section V of the Software
Architecture, and should be added to the ERD in the next documentation update.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    anomaly_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # 'Unusual Consumption' | 'Possible Fraud' | 'Meter Error' | 'Abnormal Spike'
    type: Mapped[str] = mapped_column(String(60), nullable=False)

    # 'low' | 'medium' | 'high' | 'critical'
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    # Human-readable magnitude shown in the UI, e.g. "+42%" or "Offline"
    value: Mapped[str] = mapped_column(String(40), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)  # raw model score

    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    customer = relationship("Customer", back_populates="anomalies")
