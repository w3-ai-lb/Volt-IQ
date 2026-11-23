"""
The supply side of an ishtirak network: what produces electricity, where it
goes, and what the controllers report while it happens.

WHY THESE ARE NEW TABLES AND NOT COLUMNS ON SOMETHING EXISTING
--------------------------------------------------------------
The platform's original model has customers and their consumption, which is
the demand side only. It has no representation of the thing that generates the
electricity or of the street it travels down, so it cannot express the one
question this project exists to answer: the generator sent X kWh into Al-Wadi,
the meters in Al-Wadi accounted for Y, where did X - Y go.

The zone is the join. The feeder labels on the ComAp panel are neighbourhood
names and they match these rows, which is what lets a generator reading and a
customer's bill be compared at all.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Generator(Base):
    """One diesel generating set, as listed in generators.csv."""

    __tablename__ = "generators"

    generator_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)

    capacity_kva: Mapped[float] = mapped_column(Float, default=0.0)
    capacity_kw: Mapped[float] = mapped_column(Float, default=0.0)

    # Dispatch order: 1 runs first, and the rest come on as load rises.
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Whether the engine control unit is wired to the controller. On the site
    # examined this is true for ONE generator in seven, and it decides whether
    # fuel rate, coolant temperature, oil pressure and engine speed exist at
    # all for this machine. Anything derived from those figures, litres per
    # kWh above all, can only be reported for the generators where this is
    # true, and must say so rather than averaging over the fleet.
    ecu_connected: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="active")

    # From the panel photographs: the site is "Rahal Local Pro", the
    # controllers are ComAp InteliGen 200 with InteliATS PWR on the feeders.
    # Null until confirmed for a given machine rather than assumed for all.
    site_name: Mapped[str | None] = mapped_column(String(80))
    controller_model: Mapped[str | None] = mapped_column(String(60))

    zones = relationship("Zone", back_populates="generator")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Generator {self.generator_id} {self.name} {self.capacity_kw}kW>"


class Zone(Base):
    """
    One neighbourhood fed by one generator.

    Zones are the natural controls for each other: same generator, same month,
    same weather, same tariff, different loss. That comparison is what makes
    the analysis possible without installing any new hardware, so `area_type`,
    `altitude_band` and `avg_distance_m` are not decoration, they are the
    variables a loss difference has to be explained against before anybody is
    accused of anything.
    """

    __tablename__ = "zones"

    zone_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    area_type: Mapped[str | None] = mapped_column(String(20))        # rural | urban
    altitude_band: Mapped[str | None] = mapped_column(String(20))    # above_700m | below_700m

    generator_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("generators.generator_id", ondelete="SET NULL")
    )

    # Average metres from the generator to a subscriber. Loss follows current
    # squared and rises with cable length, so this is the first thing a high
    # loss figure should be checked against.
    avg_distance_m: Mapped[float | None] = mapped_column(Float)

    generator = relationship("Generator", back_populates="zones")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Zone {self.zone_id} {self.name}>"


class ZoneEnergyDaily(Base):
    """
    kWh delivered into one zone on one day: the PRODUCED side of the equation.

    Everything else in this project is a comparison against this table.
    """

    __tablename__ = "zone_energy_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("zones.zone_id", ondelete="CASCADE"), nullable=False
    )
    generator_id: Mapped[str | None] = mapped_column(String(10))
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    energy_delivered_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    supply_hours: Mapped[float | None] = mapped_column(Float)
    peak_current_a: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_zone_energy_zone_date", "zone_id", "date"),
        Index("ix_zone_energy_date", "date"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ZoneEnergyDaily {self.zone_id} {self.date} {self.energy_delivered_kwh}kWh>"


class GeneratorTelemetry(Base):
    """
    One hourly sample from a ComAp controller.

    Every engine field below is nullable ON PURPOSE. Six of the seven
    generators have no ECU link, so their fuel rate, coolant temperature, oil
    pressure and engine speed arrive empty, and the controller shows #### on
    the panel. Storing those as 0.0 would be a lie that averages beautifully:
    a fleet fuel-efficiency figure computed over six zeroes and one real
    reading looks like a number and means nothing. Null is the honest value,
    and every query over these columns has to exclude it deliberately.

    The three per-phase currents are what phase imbalance is computed from,
    and imbalance is one of the few loss causes that can be seen from a desk
    and fixed in an afternoon.
    """

    __tablename__ = "generator_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generator_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("generators.generator_id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # --- electrical: reported by every controller ---------------------------
    active_power_kw: Mapped[float | None] = mapped_column(Float)
    load_pct: Mapped[float | None] = mapped_column(Float)
    frequency_hz: Mapped[float | None] = mapped_column(Float)

    current_l1: Mapped[float | None] = mapped_column(Float)
    current_l2: Mapped[float | None] = mapped_column(Float)
    current_l3: Mapped[float | None] = mapped_column(Float)

    voltage_l1: Mapped[float | None] = mapped_column(Float)
    voltage_l2: Mapped[float | None] = mapped_column(Float)
    voltage_l3: Mapped[float | None] = mapped_column(Float)

    power_factor: Mapped[float | None] = mapped_column(Float)

    # --- engine: ONLY where ecu_connected is true ---------------------------
    engine_run_hours: Mapped[float | None] = mapped_column(Float)
    fuel_rate_lph: Mapped[float | None] = mapped_column(Float)
    coolant_temp_c: Mapped[float | None] = mapped_column(Float)
    oil_pressure_bar: Mapped[float | None] = mapped_column(Float)
    engine_speed_rpm: Mapped[float | None] = mapped_column(Float)

    # --- on the real InteliSCADA panel, absent from the synthetic export -----
    # Read off the photographs of the live "Rahal Local Pro / All Generators"
    # screen. The practice dataset does not contain them, so they are null for
    # every row loaded today, and they exist so that the first real
    # InteliMonitor export has somewhere to land instead of being trimmed to
    # fit a schema that was built around a stand-in.
    #
    # Nothing may assume these are populated. They are additional evidence
    # when they arrive, never a requirement.
    fuel_delivery_pressure_bar: Mapped[float | None] = mapped_column(Float)   # P-FuelDelivery
    intake_manifold_temp_c: Mapped[float | None] = mapped_column(Float)       # T-IntManifold
    intake_pressure_bar: Mapped[float | None] = mapped_column(Float)          # P-Intake
    battery_voltage: Mapped[float | None] = mapped_column(Float)              # the V beside the Hz

    # The panel's own words for what the set is doing, kept verbatim rather
    # than mapped to a tidy enum: "Loaded", "MultiIslOp", "Ready", "BrksOff",
    # "NotReady". An operator recognises these, and a value nobody has seen
    # before should reach the screen intact rather than be flattened into
    # "unknown" on its way through.
    breaker_state: Mapped[str | None] = mapped_column(String(30))
    control_mode: Mapped[str | None] = mapped_column(String(10))              # OFF | MAN | AUTO | TEST

    maintenance_timer_1_h: Mapped[float | None] = mapped_column(Float)
    maintenance_timer_2_h: Mapped[float | None] = mapped_column(Float)
    active_alarm_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_telemetry_generator_time", "generator_id", "timestamp"),
        Index("ix_telemetry_time", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GeneratorTelemetry {self.generator_id} {self.timestamp}>"


class GeneratorAlarm(Base):
    """An entry from the controller's alarm and event log."""

    __tablename__ = "generator_alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generator_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("generators.generator_id", ondelete="CASCADE"), nullable=False
    )
    generator_name: Mapped[str | None] = mapped_column(String(60))
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    severity: Mapped[str | None] = mapped_column(String(20))    # warning | alarm | ...
    message: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (Index("ix_alarm_generator_time", "generator_id", "timestamp"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GeneratorAlarm {self.generator_id} {self.severity} {self.message!r}>"


class SupplySession(Base):
    """
    How many days a generator supplied a zone, and for how many hours a day.

    An ishtirak does not run around the clock. A zone that was supplied for
    ten hours a day cannot be compared with one supplied for fourteen without
    this, and comparing them anyway is a good way to invent a loss difference
    that is really a schedule difference.
    """

    __tablename__ = "supply_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generator_id: Mapped[str] = mapped_column(String(10), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(10), nullable=False)

    total_days: Mapped[int] = mapped_column(Integer, default=0)
    avg_supply_hours: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (Index("ix_supply_generator_zone", "generator_id", "zone_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SupplySession {self.generator_id}->{self.zone_id} {self.avg_supply_hours}h/day>"


class UnbilledConnection(Base):
    """
    Electricity the owner gives away or uses himself: the control room, the
    fuel pump, the office, the mosque.

    This is not theft, and the briefing is specific about why it belongs in
    the database: unrecorded, it shows up as missing energy and pollutes every
    figure downstream. Recorded here, that part of the gap stops being a
    mystery and becomes a line item the owner already knew about.
    """

    __tablename__ = "unbilled_connections"

    connection_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("zones.zone_id", ondelete="SET NULL")
    )
    est_kwh_per_month: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UnbilledConnection {self.connection_id} {self.description!r}>"
