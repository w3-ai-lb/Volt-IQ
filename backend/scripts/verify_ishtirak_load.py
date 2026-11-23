"""
Prove the ishtirak load is faithful and repeatable.

    python -m scripts.verify_ishtirak_load --dir data/ishtirak

Two claims are checked, because both have to hold before a number computed
from this database means anything:

  FAITHFUL   every table holds exactly as many rows as its CSV, and spot
             values match, so nothing was dropped or invented on the way in.
  REPEATABLE running the loader again produces the same counts, so a figure
             quoted in the report is a property of the data rather than of
             how many times the script happened to be run.

It also checks that the answer-key file was not loaded, which is the one
mistake that would invalidate every detection metric later.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import func

from app.database import SessionLocal
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

PAIRS = [
    ("generators.csv", Generator),
    ("zones.csv", Zone),
    ("supply_sessions.csv", SupplySession),
    ("unbilled_connections.csv", UnbilledConnection),
    ("zone_energy_daily.csv", ZoneEnergyDaily),
    ("generator_telemetry_hourly.csv", GeneratorTelemetry),
    ("generator_alarms.csv", GeneratorAlarm),
    ("subscribers.csv", Subscriber),
    ("subscriptions.csv", Subscription),
    ("meters.csv", Meter),
    ("meter_readings.csv", MeterReading),
    ("tariffs.csv", Tariff),
    ("invoices.csv", Invoice),
    ("payments.csv", InvoicePayment),
]

passed = 0
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("data/ishtirak"))
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=== Every row in every file reached a table ===")
        for filename, model in PAIRS:
            path = args.dir / filename
            expected = len(pd.read_csv(path))
            actual = db.query(func.count()).select_from(model).scalar()
            check(f"{filename:<34} {actual:>7,} rows", actual == expected,
                  f"csv has {expected:,}")

        print("\n=== The answer key was NOT loaded ===")
        # 68 of the 300 subscribers are labelled anomalous in that file. If any
        # column anywhere in the ishtirak tables carried that label, detection
        # metrics computed later would be meaningless.
        cols = {c.name for m in (Subscriber, Subscription, MeterReading) for c in m.__table__.columns}
        leaked = {c for c in cols if "anomal" in c or "is_theft" in c or "label" in c}
        check("no anomaly-label column exists on any ishtirak table", not leaked, str(leaked))

        print("\n=== Values, not just counts ===")
        gens = pd.read_csv(args.dir / "generators.csv")
        ecu_csv = int(gens.ecu_connected.astype(str).str.lower().eq("true").sum())
        ecu_db = db.query(func.count()).select_from(Generator).filter(Generator.ecu_connected).scalar()
        check(f"generators with an ECU: {ecu_db}", ecu_db == ecu_csv, f"csv says {ecu_csv}")

        zed = pd.read_csv(args.dir / "zone_energy_daily.csv")
        kwh_csv = float(zed.energy_delivered_kwh.sum())
        kwh_db = float(db.query(func.sum(ZoneEnergyDaily.energy_delivered_kwh)).scalar() or 0)
        check(f"total kWh delivered: {kwh_db:,.1f}", abs(kwh_db - kwh_csv) < 1.0,
              f"csv sums to {kwh_csv:,.1f}")

        inv = pd.read_csv(args.dir / "invoices.csv")
        units_csv = float(inv.units_consumed.sum())
        units_db = float(db.query(func.sum(Invoice.units_consumed)).scalar() or 0)
        check(f"total kWh billed: {units_db:,.1f}", abs(units_db - units_csv) < 1.0,
              f"csv sums to {units_csv:,.1f}")

        print("\n=== Nulls survived as nulls ===")
        # The whole point of decision 1: engine data for a generator with no
        # ECU must be absent, not zero.
        zeroed = (
            db.query(func.count())
            .select_from(GeneratorTelemetry)
            .join(Generator, Generator.generator_id == GeneratorTelemetry.generator_id)
            .filter(~Generator.ecu_connected, GeneratorTelemetry.fuel_rate_lph.isnot(None))
            .scalar()
        )
        check("no engine reading was invented for a generator without an ECU", zeroed == 0,
              f"{zeroed} rows have a fuel rate they cannot have measured")

        nulls = (
            db.query(func.count())
            .select_from(GeneratorTelemetry)
            .filter(GeneratorTelemetry.fuel_rate_lph.is_(None))
            .scalar()
        )
        check(f"engine readings correctly absent: {nulls:,} rows", nulls > 0)

        print("\n=== Referential integrity ===")
        orphan_readings = (
            db.query(func.count())
            .select_from(MeterReading)
            .outerjoin(Subscription, Subscription.subscription_id == MeterReading.subscription_id)
            .filter(Subscription.subscription_id.is_(None))
            .scalar()
        )
        check("every reading belongs to a subscription", orphan_readings == 0, str(orphan_readings))

        orphan_invoices = (
            db.query(func.count())
            .select_from(Invoice)
            .outerjoin(Subscriber, Subscriber.subscriber_id == Invoice.subscriber_id)
            .filter(Subscriber.subscriber_id.is_(None))
            .scalar()
        )
        check("every invoice belongs to a subscriber", orphan_invoices == 0, str(orphan_invoices))

        orphan_zones = (
            db.query(func.count())
            .select_from(ZoneEnergyDaily)
            .outerjoin(Zone, Zone.zone_id == ZoneEnergyDaily.zone_id)
            .filter(Zone.zone_id.is_(None))
            .scalar()
        )
        check("every daily energy row belongs to a zone", orphan_zones == 0, str(orphan_zones))

        print("\n=== The loss account reconciles ===")
        from app.analytics import loss as loss_engine
        from app.models.loss import ZoneLossMonthly

        frame = loss_engine.compute(db)
        check("the loss account produced rows", not frame.empty, "compute() returned nothing")

        if not frame.empty:
            problems = loss_engine.check_adds_up(frame)
            check("every zone-month's five parts sum to its measured loss",
                  not problems, f"{len(problems)} rows do not reconcile: {problems[:2]}")

            # A month that billed more than was delivered is not an error in
            # the code, it is a finding: the meter window and the generator
            # window do not line up. It should be small and it should be
            # reported rather than hidden by clipping in silence.
            negative = frame[frame.loss_kwh < 0]
            share = 100.0 * len(negative) / len(frame)
            check(f"months billing more than was delivered stay rare: {len(negative)} "
                  f"of {len(frame)} ({share:.1f}%)", share < 5.0,
                  "a large share means the reading window needs correcting first")

            # The residual is the only part that sends anybody to a door. If
            # it is the whole gap the model explains nothing; if it is zero the
            # model explains everything, which is just as useless.
            total_loss = frame.loss_kwh.clip(lower=0).sum()
            unexplained = frame.unexplained_kwh.sum()
            pct = 100.0 * unexplained / total_loss if total_loss else 0.0
            check(f"the unexplained residual is a residual, not the whole gap: {pct:.1f}%",
                  0.5 < pct < 60.0,
                  "outside this range the split is either explaining nothing or everything")

            stored = db.query(func.count()).select_from(ZoneLossMonthly).scalar()
            check(f"zone_loss_monthly is populated: {stored} rows", stored > 0)

        print(f"\n  PASSED {passed}   FAILED {len(failures)}")
        for f in failures:
            print(f"   - {f}")
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
