"""
Entity 5, Forecasts.

Note (from Section VII of the Software Architecture):
"The Forecast entity stores system-wide demand predictions and is therefore
not tied to an individual customer.", hence no customer_id column here.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    forecast_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    label: Mapped[str] = mapped_column(String(40), nullable=False)     # "Week 1"
    period_start: Mapped[datetime | None] = mapped_column(DateTime)

    actual: Mapped[float | None] = mapped_column(Float)                # None for future periods
    predicted: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[float] = mapped_column(Float, nullable=False)
    upper_bound: Mapped[float] = mapped_column(Float, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)      # %
    model_name: Mapped[str] = mapped_column(String(40), default="SARIMA")

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Forecast {self.label} predicted={self.predicted}>"
