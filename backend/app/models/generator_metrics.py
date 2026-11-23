"""
Per-generator, per-month figures, computed once and stored.

WHY A TABLE AND NOT A QUERY
---------------------------
FR-2.14: "Pre-computed metrics. Do not make the LLM calculate. Calculate loss
%, litres per kWh and zone rankings in advance, store them in tables, and let
the LLM read them."

There is a second reason, and it is a correctness one rather than a speed one.
Phase imbalance is the mean of each hour's imbalance, and that is not the same
number as the imbalance of the mean currents. Averaging L1, L2 and L3 first
cancels out every hour where the heavy phase was a different one, and a
generator whose imbalance moves around comes out looking perfectly balanced.
Computing it the wrong way in SQL gave five of the seven sets an imbalance of
0.1% when the true figure is 5%.

Doing it per sample needs either a row-wise max and min of three columns, which
is spelled differently in SQLite and PostgreSQL, or a pass in pandas. The pass
happens here, once, and the dashboard reads the answer.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GeneratorMonthMetrics(Base):
    __tablename__ = "generator_month_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generator_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("generators.generator_id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date_type] = mapped_column(Date, nullable=False)

    # FR-2.1
    produced_kwh: Mapped[float] = mapped_column(Float, default=0.0)

    # FR-2.4. Taken from the measured supply hours of the zones this set feeds,
    # not from counting telemetry rows: the controller is sampled on a schedule
    # that is a property of the logger, not of the engine.
    supply_hours: Mapped[float | None] = mapped_column(Float)

    # FR-2.5. Null where the ECU is not connected. Six sets in seven.
    fuel_litres: Mapped[float | None] = mapped_column(Float)
    litres_per_kwh: Mapped[float | None] = mapped_column(Float)
    ecu_connected: Mapped[bool] = mapped_column(Boolean, default=False)

    # FR-2.6. The MEAN OF THE HOURLY IMBALANCES, for the reason in the module
    # docstring. `hours_above_flag_pct` is what turns a single average into
    # something actionable: 30% for one hour a month is a curiosity, 30% for
    # a quarter of all hours is a standing fault.
    phase_imbalance_pct: Mapped[float | None] = mapped_column(Float)
    hours_above_flag_pct: Mapped[float | None] = mapped_column(Float)

    # FR-2.7
    alarm_count: Mapped[int] = mapped_column(Integer, default=0)

    computed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_genmetrics_generator_month", "generator_id", "month", unique=True),
        Index("ix_genmetrics_month", "month"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GeneratorMonthMetrics {self.generator_id} {self.month}>"
