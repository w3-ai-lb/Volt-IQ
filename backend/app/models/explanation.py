"""
What a subscriber said when asked why their consumption changed.

WHY THIS TABLE IS THE MOST VALUABLE THING IN PHASE 4
----------------------------------------------------
    "Remember: nobody has a list of confirmed theft cases. This is how you
     build one. Each answer improves the next model."

Every detection figure in this project is measured against labels that came
with a synthetic dataset. On a real network there are none, and there is no
way to get them except by asking. A flag says a pattern is unusual; only the
person behind the meter knows whether they travelled for two months, whether
the air conditioner broke, or whether nothing changed at all.

So each answer is stored with the flag that prompted it, and `resolved_as`
turns a conversation into a training label. After a year of this the owner has
something no model could have inferred and no dataset could have supplied.

`resolved_as` is deliberately coarse: explained, unexplained, or unknown. It
does not have a value meaning theft, because a conversation cannot establish
that and a column that offers the option invites somebody to record it.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# What an answer resolved a flag into. "unexplained" means the subscriber
# offered no change that accounts for it, which is a reason to visit and
# still not a finding.
RESOLUTIONS = ("explained", "unexplained", "unknown")


class SubscriberExplanation(Base):
    __tablename__ = "subscriber_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("subscribers.subscriber_id", ondelete="CASCADE"), nullable=False
    )

    # The rule that raised the flag, and the evidence shown at the time, so the
    # answer can be read against what was actually asked months later.
    rule: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[str | None] = mapped_column(Text)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)

    resolved_as: Mapped[str] = mapped_column(String(20), default="unknown")
    asked_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ix_explanation_subscriber", "subscriber_id", "asked_at"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SubscriberExplanation {self.subscriber_id} {self.resolved_as}>"
