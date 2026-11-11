"""
The tariff plans, in one place.

Both the seeder and the ingest loader need to agree on what a plan is, and
importing one from the other set up a circular import waiting to happen. The
load-profile logic branches on this value, so a dataset spelling it
"commercial" would otherwise be modelled as a household.
"""

from __future__ import annotations

PLANS: tuple[str, ...] = ("Residential", "Commercial", "Industrial")


def normalise_plan(plan: str | None) -> str:
    """Map a free-text plan value onto one of the three known plans."""
    if not plan:
        return "Residential"
    cleaned = str(plan).strip().lower()
    for known in PLANS:
        if cleaned == known.lower():
            return known
    return "Residential"
