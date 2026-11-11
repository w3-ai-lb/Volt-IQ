"""
Phase 1 of Project 3: load the ishtirak dataset into the platform database.

    python -m app.pipeline.ishtirak --dir data/ishtirak
    python -m app.pipeline.ishtirak --dir data/ishtirak --fresh --yes

WHAT THIS IS
------------
One repeatable script, not a sequence of manual steps, that reads all fourteen
files the supervisor supplied and writes them into one database with nothing
dropped and nothing invented. Running it twice gives the same database, which
is the only reason a figure computed from it can be defended.

EVERY CLEANING DECISION IS DOCUMENTED WHERE IT HAPPENS
------------------------------------------------------
The briefing says each one will have to be justified at the defence, so each
one is written down at the line that makes it rather than in a document that
drifts away from the code. Search for DECISION to find them all; the loader
also prints a numbered summary of them when it finishes, so the report can
quote it.

THE LABEL FILE IS EVALUATION DATA, AND IT IS KEPT OUT OF HERE
------------------------------------------------------------
subscriber_labels_for_intern.csv, and the byte-identical
GROUND_TRUTH_subscribers.csv beside it, mark which subscribers show abnormal
behaviour. The supervisor sent them deliberately, so having them is not a
mistake; the written briefing had said they would be withheld, and his voice
note supersedes that.

They are still not loaded into these tables, for a different and better
reason. Anything that reaches the feature tables can end up in a rule, a
threshold or a model input, and a detector tuned on the labels it is later
scored against reports a number that measures nothing. Keeping them in a
separate file, read only when detection is being scored, is what lets a
precision figure in the report survive the question "did you have the answers
while you were building?".

They also say abnormal behaviour rather than theft, which is the supervisor's
own preference: a sharp drop in consumption can be a short circuit, a broken
air conditioner, or somebody on the next line, and the data cannot tell those
apart.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_all_tables
from app.models.invoice import Invoice, InvoicePayment, Tariff
from app.models.network import (
    Generator,
    GeneratorAlarm,
    GeneratorTelemetry,
    SupplySession,
    UnbilledConnection,
    Zone,
    ZoneEnergyDaily,
)
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("ishtirak")

# Evaluation data. Read when detection is SCORED, never when it is built.
EVALUATION_ONLY = {
    "ground_truth_subscribers.csv",
    "subscriber_labels_for_intern.csv",
}

# The order matters: a child row cannot be written before the row it points at.
FILE_ORDER = [
    "generators.csv",
    "zones.csv",
    "supply_sessions.csv",
    "unbilled_connections.csv",
    "zone_energy_daily.csv",
    "generator_telemetry_hourly.csv",
    "generator_alarms.csv",
    "subscribers.csv",
    "subscriptions.csv",
    "meters.csv",
    "meter_readings.csv",
    "tariffs.csv",
    "invoices.csv",
    "payments.csv",
]

# Filled in as the load runs, printed at the end, quotable in the report.
DECISIONS: list[str] = []


def decide(note: str) -> None:
    """Record a cleaning decision, once, in the order it was taken."""
    if note not in DECISIONS:
        DECISIONS.append(note)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------
def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _as_date(value) -> date | None:
    if pd.isna(value):
        return None
    return pd.to_datetime(value).date()


def _as_datetime(value) -> datetime | None:
    if pd.isna(value):
        return None
    return pd.to_datetime(value).to_pydatetime()


def _as_float(value) -> float | None:
    """
    DECISION: an empty numeric cell stays None, it does not become 0.0.

    Six of the seven generators have no ECU link, so their engine columns are
    blank. Written as zero they average beautifully into a fleet fuel figure
    that is arithmetically valid and completely false. None forces every query
    over those columns to exclude them on purpose.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return None
    return float(value)


def _as_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}
    return bool(value)


def _chunks(rows: list, size: int = 5000) -> Iterable[list]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


# ---------------------------------------------------------------------------
# Loaders, one per file
# ---------------------------------------------------------------------------
def load_generators(db: Session, path: Path) -> int:
    df = _read(path)
    without_ecu = (~df.ecu_connected.map(_as_bool)).sum()
    if without_ecu:
        decide(
            f"{without_ecu} of {len(df)} generators have ecu_connected = false. Their engine "
            "readings are stored as NULL rather than 0, so fuel-per-kWh is reported only for "
            "the generators that actually measure it, and is labelled as covering those."
        )
    for _, r in df.iterrows():
        db.merge(
            Generator(
                generator_id=str(r.generator_id),
                name=str(r["name"]),
                capacity_kva=_as_float(r.get("capacity_kva")) or 0.0,
                capacity_kw=_as_float(r.get("capacity_kw")) or 0.0,
                priority=int(r.priority) if not pd.isna(r.get("priority")) else 0,
                ecu_connected=_as_bool(r.get("ecu_connected")),
                status=str(r.get("status") or "active"),
            )
        )
    return len(df)


def load_zones(db: Session, path: Path) -> int:
    df = _read(path)
    for _, r in df.iterrows():
        db.merge(
            Zone(
                zone_id=str(r.zone_id),
                name=str(r["name"]),
                area_type=str(r.area_type) if not pd.isna(r.get("area_type")) else None,
                altitude_band=str(r.altitude_band) if not pd.isna(r.get("altitude_band")) else None,
                generator_id=str(r.generator_id) if not pd.isna(r.get("generator_id")) else None,
                avg_distance_m=_as_float(r.get("avg_distance_m")),
            )
        )
    return len(df)


def load_supply_sessions(db: Session, path: Path) -> int:
    df = _read(path)
    rows = [
        SupplySession(
            generator_id=str(r.generator_id),
            zone_id=str(r.zone_id),
            total_days=int(r.total_days) if not pd.isna(r.get("total_days")) else 0,
            avg_supply_hours=_as_float(r.get("avg_supply_hours")),
        )
        for _, r in df.iterrows()
    ]
    db.add_all(rows)
    decide(
        "Supply hours differ between zones, so two zones are never compared on total kWh "
        "alone. A zone supplied 14 hours a day and one supplied 12 will differ by about a "
        "sixth before anything at all is wrong with either."
    )
    return len(rows)


def load_unbilled_connections(db: Session, path: Path) -> int:
    df = _read(path)
    total = 0.0
    for _, r in df.iterrows():
        est = _as_float(r.get("est_kwh_per_month")) or 0.0
        total += est
        db.merge(
            UnbilledConnection(
                connection_id=str(r.connection_id),
                description=str(r.description),
                zone_id=str(r.zone_id) if not pd.isna(r.get("zone_id")) else None,
                est_kwh_per_month=est,
            )
        )
    decide(
        f"{len(df)} unbilled connections totalling about {total:,.0f} kWh a month are loaded as "
        "a known, named part of the gap. They are the owner's own supply, not loss, and leaving "
        "them out would push that energy into the unexplained residual where it would look "
        "like somebody taking it."
    )
    return len(df)


def load_zone_energy_daily(db: Session, path: Path) -> int:
    df = _read(path)
    rows = [
        ZoneEnergyDaily(
            zone_id=str(r.zone_id),
            generator_id=str(r.generator_id) if not pd.isna(r.get("generator_id")) else None,
            date=_as_date(r.date),
            energy_delivered_kwh=_as_float(r.get("energy_delivered_kwh")) or 0.0,
            supply_hours=_as_float(r.get("supply_hours")),
            peak_current_a=_as_float(r.get("peak_current_a")),
        )
        for _, r in df.iterrows()
    ]
    for chunk in _chunks(rows):
        db.add_all(chunk)
        db.flush()
    decide(
        "zone_energy_daily is treated as the authoritative PRODUCED figure. It is the only "
        "measurement of what left the generator for a given neighbourhood, so every loss "
        "number in the system is a comparison against this table."
    )
    return len(rows)


def load_telemetry(db: Session, path: Path) -> int:
    df = _read(path)
    engine_cols = [
        "engine_run_hours",
        "fuel_rate_lph",
        "coolant_temp_c",
        "oil_pressure_bar",
        "engine_speed_rpm",
    ]
    panel_only = [
        "p_fueldelivery",
        "t_intmanifold",
        "p_intake",
        "battery_voltage",
        "breaker_state",
        "control_mode",
        "maintenance_timer_1_h",
        "maintenance_timer_2_h",
    ]
    absent = [c for c in panel_only if c not in df.columns]
    if absent:
        decide(
            f"{len(absent)} fields visible on the live InteliSCADA panel are not in this export "
            f"({', '.join(absent)}). Columns exist for them and are left NULL. They were read off "
            "the photographs of the real screen, so the first genuine InteliMonitor export lands "
            "without a schema change, and nothing in the code may assume they are populated."
        )

    missing = df[engine_cols].isna().mean().mean() * 100
    decide(
        f"{missing:.0f}% of engine-telemetry cells are empty across the fleet, because the ECU "
        "link exists on one generator. They are stored as NULL. Any fleet-level fuel figure "
        "computed from this table is a figure for the generators that report, and the "
        "interface must say which."
    )

    rows = [
        GeneratorTelemetry(
            generator_id=str(r.generator_id),
            timestamp=_as_datetime(r.timestamp),
            active_power_kw=_as_float(r.get("active_power_kw")),
            load_pct=_as_float(r.get("load_pct")),
            frequency_hz=_as_float(r.get("frequency_hz")),
            current_l1=_as_float(r.get("current_l1")),
            current_l2=_as_float(r.get("current_l2")),
            current_l3=_as_float(r.get("current_l3")),
            voltage_l1=_as_float(r.get("voltage_l1")),
            voltage_l2=_as_float(r.get("voltage_l2")),
            voltage_l3=_as_float(r.get("voltage_l3")),
            power_factor=_as_float(r.get("power_factor")),
            engine_run_hours=_as_float(r.get("engine_run_hours")),
            fuel_rate_lph=_as_float(r.get("fuel_rate_lph")),
            coolant_temp_c=_as_float(r.get("coolant_temp_c")),
            oil_pressure_bar=_as_float(r.get("oil_pressure_bar")),
            engine_speed_rpm=_as_float(r.get("engine_speed_rpm")),
            # Present on the live InteliSCADA panel, absent from this
            # practice export. Read through the same tolerant .get() so a
            # real InteliMonitor CSV populates them without a code change,
            # and so their absence today is silent rather than fatal.
            fuel_delivery_pressure_bar=_as_float(
                r.get("p_fueldelivery") if "p_fueldelivery" in r else r.get("fuel_delivery_pressure_bar")
            ),
            intake_manifold_temp_c=_as_float(
                r.get("t_intmanifold") if "t_intmanifold" in r else r.get("intake_manifold_temp_c")
            ),
            intake_pressure_bar=_as_float(
                r.get("p_intake") if "p_intake" in r else r.get("intake_pressure_bar")
            ),
            battery_voltage=_as_float(r.get("battery_voltage")),
            breaker_state=str(r.breaker_state) if not pd.isna(r.get("breaker_state")) else None,
            control_mode=str(r.control_mode) if not pd.isna(r.get("control_mode")) else None,
            maintenance_timer_1_h=_as_float(r.get("maintenance_timer_1_h")),
            maintenance_timer_2_h=_as_float(r.get("maintenance_timer_2_h")),
        )
        for _, r in df.iterrows()
    ]
    for chunk in _chunks(rows):
        db.add_all(chunk)
        db.flush()
    return len(rows)


def load_alarms(db: Session, path: Path) -> int:
    df = _read(path)
    rows = [
        GeneratorAlarm(
            generator_id=str(r.generator_id),
            generator_name=str(r.generator_name) if not pd.isna(r.get("generator_name")) else None,
            timestamp=_as_datetime(r.timestamp),
            severity=str(r.severity) if not pd.isna(r.get("severity")) else None,
            message=str(r.message) if not pd.isna(r.get("message")) else None,
        )
        for _, r in df.iterrows()
    ]
    db.add_all(rows)
    return len(rows)


def load_subscribers(db: Session, path: Path) -> int:
    df = _read(path)
    for _, r in df.iterrows():
        db.merge(
            Subscriber(
                subscriber_id=str(r.subscriber_id),
                zone_id=str(r.zone_id) if not pd.isna(r.get("zone_id")) else None,
                subscriber_type=str(r.subscriber_type) if not pd.isna(r.get("subscriber_type")) else None,
            )
        )
    decide(
        "Subscribers are loaded without login credentials. A subscriber is a record the "
        "provider holds; it becomes an account only if somebody registers for one, which is "
        "why subscribers and customers are separate tables."
    )
    return len(df)


def load_subscriptions(db: Session, path: Path) -> int:
    df = _read(path)
    statuses = df.status.value_counts().to_dict()
    if len(statuses) == 1:
        decide(
            f"Every subscription row carries status = {list(statuses)[0]!r}. The contract table "
            "holds TODAY's status, so the disconnected-but-consuming rule reads "
            "meter_readings.subscription_status, which is the status at the time of reading. "
            "Using this column instead would find nothing and look like a clean result."
        )
    for _, r in df.iterrows():
        db.merge(
            Subscription(
                subscription_id=str(r.subscription_id),
                subscriber_id=str(r.subscriber_id),
                generator_id=str(r.generator_id) if not pd.isna(r.get("generator_id")) else None,
                zone_id=str(r.zone_id) if not pd.isna(r.get("zone_id")) else None,
                ampere_capacity=_as_float(r.get("ampere_capacity")),
                phase_type=str(r.phase_type) if not pd.isna(r.get("phase_type")) else None,
                billing_model=str(r.billing_model) if not pd.isna(r.get("billing_model")) else None,
                status=str(r.get("status") or "active"),
            )
        )
    return len(df)


def load_meters(db: Session, path: Path) -> int:
    df = _read(path)
    for _, r in df.iterrows():
        db.merge(
            Meter(
                meter_id=str(r.meter_id),
                subscription_id=str(r.subscription_id),
                serial_number=str(r.serial_number) if not pd.isna(r.get("serial_number")) else None,
                meter_type=str(r.meter_type) if not pd.isna(r.get("meter_type")) else None,
                digit_count=int(r.digit_count) if not pd.isna(r.get("digit_count")) else None,
                multiplier=_as_float(r.get("multiplier")) or 1.0,
                initial_reading=_as_float(r.get("initial_reading")),
            )
        )
    decide(
        "Meter digit_count is kept so that a reading lower than the previous one can be tested "
        "for dial rollover before it is called a reversed meter. A five-digit meter passing "
        "99999 looks exactly like tampering if the digit count is thrown away."
    )
    return len(df)


def load_meter_readings(db: Session, path: Path) -> int:
    df = _read(path)

    low_ocr = int((df.ocr_confidence < 0.80).sum()) if "ocr_confidence" in df else 0
    corrected = int(df.was_corrected.map(_as_bool).sum()) if "was_corrected" in df else 0
    if low_ocr or corrected:
        decide(
            f"{low_ocr} readings carry an OCR confidence below 0.80 and {corrected} are flagged "
            "as corrected. They are loaded unchanged, with the confidence beside them. A "
            "low-confidence reading is suspect, not wrong, and deleting it would silently "
            "reduce billed energy and inflate the loss it was supposed to explain."
        )

    if "reading_date" in df and "billing_period" in df:
        d = df.copy()
        d["reading_date"] = pd.to_datetime(d.reading_date)
        d["billing_period"] = pd.to_datetime(d.billing_period)
        spread = d.groupby("billing_period").reading_date.agg(lambda s: (s.max() - s.min()).days)
        decide(
            f"Meters within one billing period are read over {spread.mean():.0f} days on average "
            f"(worst {spread.max()}). The generator's month and the meter's month are therefore "
            "different windows. reading_date is kept so this can be corrected for, and until it "
            "is, the monthly loss figure carries a known timing error of a few percent."
        )

    rows = [
        MeterReading(
            reading_id=str(r.reading_id),
            meter_id=str(r.meter_id),
            subscription_id=str(r.subscription_id),
            billing_period=_as_date(r.billing_period),
            reading_value=_as_float(r.get("reading_value")) or 0.0,
            capture_method=str(r.capture_method) if not pd.isna(r.get("capture_method")) else None,
            ocr_confidence=_as_float(r.get("ocr_confidence")),
            was_corrected=_as_bool(r.get("was_corrected")),
            subscription_status=str(r.subscription_status)
            if not pd.isna(r.get("subscription_status"))
            else None,
            reading_date=_as_date(r.get("reading_date")),
        )
        for _, r in df.iterrows()
    ]
    for chunk in _chunks(rows):
        db.add_all(chunk)
        db.flush()
    decide(
        "Readings are stored as the dial value, not as consumption. Consumption is the "
        "difference between consecutive readings, which means the first month of every meter "
        "has no consumption at all, and any total that ignores that over-counts by one reading "
        "per meter."
    )
    return len(rows)


def load_tariffs(db: Session, path: Path) -> int:
    df = _read(path)
    lo, hi = df.rate_per_kwh_base.min(), df.rate_per_kwh_base.max()
    decide(
        f"The tariff is monthly, not constant: the base rate moves between {lo:,.0f} and "
        f"{hi:,.0f} LBP/kWh across the period. Revenue in different months is therefore not "
        "comparable at a single rate, and every invoice keeps the tariff row that priced it."
    )
    for _, r in df.iterrows():
        db.merge(
            Tariff(
                tariff_id=str(r.tariff_id),
                effective_month=_as_date(r.effective_month),
                rate_per_kwh_base=_as_float(r.get("rate_per_kwh_base")) or 0.0,
                rate_per_kwh_highland=_as_float(r.get("rate_per_kwh_highland")),
                currency=str(r.get("currency") or "LBP"),
                diesel_price_per_20l=_as_float(r.get("diesel_price_per_20l")),
                usd_exchange_rate=_as_float(r.get("usd_exchange_rate")),
            )
        )
    return len(df)


def load_invoices(db: Session, path: Path) -> int:
    df = _read(path)
    rows = [
        Invoice(
            invoice_id=str(r.invoice_id),
            subscription_id=str(r.subscription_id),
            subscriber_id=str(r.subscriber_id),
            zone_id=str(r.zone_id) if not pd.isna(r.get("zone_id")) else None,
            billing_period=_as_date(r.billing_period),
            units_consumed=_as_float(r.get("units_consumed")) or 0.0,
            tariff_id=str(r.tariff_id) if not pd.isna(r.get("tariff_id")) else None,
            rate_applied=_as_float(r.get("rate_applied")),
            fixed_charge=_as_float(r.get("fixed_charge")) or 0.0,
            variable_charge=_as_float(r.get("variable_charge")) or 0.0,
            total_amount=_as_float(r.get("total_amount")) or 0.0,
            currency=str(r.get("currency") or "LBP"),
        )
        for _, r in df.iterrows()
    ]
    for chunk in _chunks(rows):
        db.add_all(chunk)
        db.flush()
    decide(
        "units_consumed on the invoice is the BILLED side of the loss equation. The money "
        "columns are not: total_amount includes a fixed subscription charge that is paid "
        "whether or not a kilowatt-hour flows, so an invoice total cannot be converted back "
        "into energy."
    )
    return len(rows)


def load_payments(db: Session, path: Path) -> int:
    df = _read(path)
    rows = [
        InvoicePayment(
            payment_id=str(r.payment_id),
            invoice_id=str(r.invoice_id) if not pd.isna(r.get("invoice_id")) else None,
            subscriber_id=str(r.subscriber_id),
            amount=_as_float(r.get("amount")) or 0.0,
            currency=str(r.get("currency") or "LBP"),
            payment_method=str(r.payment_method) if not pd.isna(r.get("payment_method")) else None,
            payment_date=_as_date(r.get("payment_date")),
            collected_by=str(r.collected_by) if not pd.isna(r.get("collected_by")) else None,
        )
        for _, r in df.iterrows()
    ]
    for chunk in _chunks(rows):
        db.add_all(chunk)
        db.flush()
    decide(
        "collected_by is kept on every payment. Collector fraud, money taken and the invoice "
        "never marked paid, is a named pattern in this business and cannot be looked for "
        "without knowing who took it."
    )
    return len(rows)


LOADERS = {
    "generators.csv": load_generators,
    "zones.csv": load_zones,
    "supply_sessions.csv": load_supply_sessions,
    "unbilled_connections.csv": load_unbilled_connections,
    "zone_energy_daily.csv": load_zone_energy_daily,
    "generator_telemetry_hourly.csv": load_telemetry,
    "generator_alarms.csv": load_alarms,
    "subscribers.csv": load_subscribers,
    "subscriptions.csv": load_subscriptions,
    "meters.csv": load_meters,
    "meter_readings.csv": load_meter_readings,
    "tariffs.csv": load_tariffs,
    "invoices.csv": load_invoices,
    "payments.csv": load_payments,
}


# ---------------------------------------------------------------------------
def _wipe_ishtirak(db: Session) -> None:
    """
    Empty only the ishtirak tables, leaving the platform's own data alone.

    The loader is re-runnable, and re-running it without this would duplicate
    every row in the tables that have surrogate keys, because those rows have
    nothing for merge() to match on.
    """
    from app.models.loss import ZoneLossMonthly

    for model in (
        ZoneLossMonthly,
        InvoicePayment,
        Invoice,
        MeterReading,
        Meter,
        Subscription,
        Subscriber,
        Tariff,
        GeneratorAlarm,
        GeneratorTelemetry,
        ZoneEnergyDaily,
        SupplySession,
        UnbilledConnection,
        Zone,
        Generator,
    ):
        db.query(model).delete()
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load the ishtirak dataset (Project 3, Phase 1).")
    parser.add_argument("--dir", type=Path, default=Path("data/ishtirak"),
                        help="Folder holding the fourteen CSV files")
    parser.add_argument("--keep", action="store_true",
                        help="Do not clear the ishtirak tables first (advanced; risks duplicates)")
    parser.add_argument("--skip-loss", action="store_true",
                        help="Load only; do not rebuild the derived loss account")
    args = parser.parse_args()

    folder: Path = args.dir
    if not folder.is_dir():
        logger.error("No such folder: %s", folder)
        return 1

    present = {p.name.lower(): p for p in folder.glob("*.csv")}

    for name in sorted(present):
        if name in EVALUATION_ONLY:
            logger.warning(
                "Not loading %s: it holds the abnormal-behaviour labels, which are for "
                "SCORING detection, not for building it. Keeping them out of these tables is "
                "what makes a precision figure mean something later.", present[name].name
            )

    missing = [f for f in FILE_ORDER if f not in present]
    if missing:
        logger.error("Missing from %s: %s", folder, ", ".join(missing))
        return 1

    create_all_tables()
    db = SessionLocal()
    counts: dict[str, int] = {}
    try:
        if not args.keep:
            _wipe_ishtirak(db)

        for name in FILE_ORDER:
            n = LOADERS[name](db, present[name])
            db.commit()
            counts[name] = n
            logger.info("%-34s %7d rows", name, n)

        # The loss account is derived from these tables, so it is stale the
        # instant they change. Rebuilding it here rather than leaving it to be
        # remembered is the difference between a dashboard that is wrong and
        # one that is merely out of date, and only one of those is visible.
        if not args.skip_loss:
            from app.analytics import generator_metrics as gen_metrics
            from app.analytics import loss as loss_engine

            written_g = gen_metrics.refresh(db)
            logger.info("%-34s %7d generator-months", "generator_month_metrics (derived)", written_g)

            frame = loss_engine.compute(db)
            written = loss_engine.store(db, frame)
            logger.info("%-34s %7d zone-months", "zone_loss_monthly (derived)", written)

            problems = loss_engine.check_adds_up(frame)
            if problems:
                logger.error(
                    "%d zone-months do not reconcile: their five parts do not sum to the "
                    "measured loss. The account is not trustworthy until this is fixed.",
                    len(problems),
                )
                for p in problems[:3]:
                    logger.error("    %s", p)

        print("\n" + "=" * 72)
        print("  LOADED")
        print("=" * 72)
        for name, n in counts.items():
            print(f"  {name:<36} {n:>8,}")
        print(f"  {'TOTAL':<36} {sum(counts.values()):>8,}")

        print("\n" + "=" * 72)
        print("  CLEANING DECISIONS  (each one is defensible, and each one is here)")
        print("=" * 72)
        for i, note in enumerate(DECISIONS, 1):
            print(f"\n  {i}. {note}")
        print()
        return 0
    except Exception as exc:
        logger.error("Load failed: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
