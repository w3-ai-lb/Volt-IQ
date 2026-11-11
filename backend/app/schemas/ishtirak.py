"""
Response shapes for the ishtirak dashboard and the question interface.

Every field here answers a numbered requirement in the traceability document,
and the requirement is named beside it. A field nobody asked for is a field
somebody has to justify at the defence.

Nullable is used with intent throughout. `None` means "not measurable from the
data we hold", which is a different statement from zero, and the interface is
required to say which one it is looking at.
"""

from datetime import date

from app.schemas.common import CamelModel


class GeneratorToday(CamelModel):
    """FR-2.1, FR-2.4, FR-2.5, FR-2.6: one row per generating set."""

    generator_id: str
    name: str
    capacity_kw: float

    # FR-2.1 energy produced
    produced_kwh_period: float
    # FR-2.4 how long it ran
    run_hours_period: float | None = None

    # FR-2.5 fuel. None where the ECU is not connected, which is six sets in
    # seven, and the screen must show that rather than a zero.
    fuel_litres_period: float | None = None
    litres_per_kwh: float | None = None
    ecu_connected: bool = False

    # FR-2.6 phase balance, flagged above 15%
    phase_imbalance_pct: float | None = None
    imbalance_flagged: bool = False

    # FR-2.7
    active_alarms: int = 0


class ZoneLossRow(CamelModel):
    """FR-2.3, FR-2.9: one zone, ranked worst first."""

    zone_id: str
    name: str
    area_type: str | None = None
    avg_distance_m: float | None = None

    delivered_kwh: float
    billed_kwh: float
    loss_kwh: float
    loss_pct: float | None = None

    # The split. NFR-1: no field is called theft; the residual is unexplained.
    normal_technical_kwh: float = 0.0
    excess_technical_kwh: float = 0.0
    measurement_kwh: float = 0.0
    unbilled_kwh: float = 0.0
    unexplained_kwh: float = 0.0
    unexplained_pct: float | None = None

    confidence: float | None = None
    # FR-2.10: the screen has to be able to explain the number it is showing.
    explanation: str


class Collections(CamelModel):
    """FR-2.8: invoiced against collected."""

    invoiced: float
    collected: float
    outstanding: float
    currency: str = "LBP"
    unpaid_invoices: int = 0


class AlarmRow(CamelModel):
    """FR-2.7."""

    generator_id: str
    generator_name: str | None = None
    timestamp: str
    severity: str | None = None
    message: str | None = None


class DashboardOut(CamelModel):
    """
    Everything the briefing lists for the owner's morning view, in one payload.

    `as_of` is not decoration. The dataset in hand ends before today, so a
    dashboard that says "today" and shows zero would be reporting a quiet night
    at the generators rather than the absence of data. This field states which
    day the figures are actually for, and the interface shows it.
    """

    as_of: date
    period_start: date
    period_end: date
    is_live: bool          # False when the newest reading predates today

    # FR-2.1 / FR-2.2
    produced_kwh: float
    billed_kwh: float
    gap_kwh: float
    # FR-2.3
    loss_pct: float | None = None

    generators: list[GeneratorToday]
    zones: list[ZoneLossRow]          # FR-2.9, worst first
    collections: Collections
    alarms: list[AlarmRow]

    # FR-2.10 / NFR-1: the sentence the briefing calls the good outcome.
    summary: str
