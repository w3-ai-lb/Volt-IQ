"""
The loss account: what one zone was sent in a month, what it was billed for,
and the five-way split of the difference.

WHY THIS IS A TABLE AND NOT A CALCULATION AT QUESTION TIME
----------------------------------------------------------
Two reasons, and the briefing gives both.

A language model must never be asked to do the arithmetic. Every figure in an
answer has to come from a query result, so the percentages, the rankings and
the split are computed in advance, stored here, and read. A model that adds up
kilowatt-hours will one day add them up wrong and say it fluently.

And the split is not a formula, it is a chain of reasoning over several tables:
the I squared R curve fitted per zone, the reading-date spread, the OCR
confidence, the unbilled connections list. Recomputing that inside a request
would be slow and, worse, would make the number on the dashboard depend on
when it was asked.

WHAT THE COLUMNS MEAN
---------------------
The five parts sum to `loss_kwh`. `unexplained_kwh` is what is left after the
other four, and it is the only one that justifies visiting anybody. The
briefing is explicit that this residual is roughly a fifth of the total, and
that a system which reports the whole gap as theft will be abandoned inside a
month. The word theft does not appear in this table on purpose.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ZoneLossMonthly(Base):
    """One zone, one month, fully accounted for."""

    __tablename__ = "zone_loss_monthly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("zones.zone_id", ondelete="CASCADE"), nullable=False
    )
    # First day of the month, so it sorts and joins like a date rather than
    # like the string "Jun 2026".
    month: Mapped[date_type] = mapped_column(Date, nullable=False)

    # --- the two measured quantities ---------------------------------------
    energy_delivered_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    units_billed_kwh: Mapped[float] = mapped_column(Float, default=0.0)

    loss_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    loss_pct: Mapped[float | None] = mapped_column(Float)

    # --- the split, in the briefing's order ---------------------------------
    # Physics. Nothing to do about it.
    normal_technical_kwh: Mapped[float | None] = mapped_column(Float)
    # Bad joints, undersized cable, phase imbalance. Send a technician.
    excess_technical_kwh: Mapped[float | None] = mapped_column(Float)
    # OCR misreads, estimated readings, the meter month against the generator
    # month. Fix the process.
    measurement_kwh: Mapped[float | None] = mapped_column(Float)
    # The control room, the office, the mosque. The owner's own choice.
    unbilled_kwh: Mapped[float | None] = mapped_column(Float)
    # What is left. A shortlist for a field visit, never a verdict.
    unexplained_kwh: Mapped[float | None] = mapped_column(Float)

    # --- how much the split itself should be trusted ------------------------
    # Low when the month is short of data: a zone with few readings, or one
    # whose generator has no ECU, gets a split that is arithmetically fine and
    # epistemically thin. The dashboard shows this rather than hiding it.
    confidence: Mapped[float | None] = mapped_column(Float)
    method_note: Mapped[str | None] = mapped_column(String(255))

    computed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_loss_zone_month", "zone_id", "month", unique=True),
        Index("ix_loss_month", "month"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ZoneLossMonthly {self.zone_id} {self.month} {self.loss_pct}%>"
