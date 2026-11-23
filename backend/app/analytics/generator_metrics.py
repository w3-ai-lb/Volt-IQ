"""
Per-generator monthly figures for the owner's dashboard (FR-2.1, 2.4, 2.5,
2.6, 2.7), computed once and stored (FR-2.14).

The three that are easy to get wrong, and how they are got right here:

PHASE IMBALANCE is the mean of each hour's imbalance, never the imbalance of
the mean currents. The second cancels out any generator whose heavy phase
moves around, which is most of them.

SUPPLY HOURS come from the measured supply hours of the zones the set feeds,
not from counting telemetry rows. The controller samples on the logger's
schedule; that schedule is a property of the logging, not of the engine.

FUEL is null wherever the ECU is not connected. Six sets in seven report
nothing, and a zero would read as a generator that burns no diesel.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.generator_metrics import GeneratorMonthMetrics
from app.models.network import Generator, GeneratorAlarm, GeneratorTelemetry, ZoneEnergyDaily

logger = logging.getLogger(__name__)

IMBALANCE_FLAG_PCT = 15.0


def _month(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.to_period("M").dt.to_timestamp().dt.date


def compute(db: Session) -> pd.DataFrame:
    gens = pd.DataFrame(
        db.query(Generator.generator_id, Generator.name, Generator.ecu_connected).all(),
        columns=["generator_id", "name", "ecu_connected"],
    )
    if gens.empty:
        return pd.DataFrame()

    # --- production and supply hours, from the zone side ---------------------
    zed = pd.DataFrame(
        db.query(
            ZoneEnergyDaily.generator_id,
            ZoneEnergyDaily.zone_id,
            ZoneEnergyDaily.date,
            ZoneEnergyDaily.energy_delivered_kwh,
            ZoneEnergyDaily.supply_hours,
        ).all(),
        columns=["generator_id", "zone_id", "date", "kwh", "supply_hours"],
    )
    if zed.empty:
        return pd.DataFrame()
    zed["month"] = _month(zed.date)

    produced = zed.groupby(["generator_id", "month"], as_index=False).kwh.sum().rename(
        columns={"kwh": "produced_kwh"}
    )
    # A set feeding three zones at once did not run three times as long, so the
    # day's hours are the longest any of its zones was supplied, not the sum.
    per_day = zed.groupby(["generator_id", "date"], as_index=False).supply_hours.max()
    per_day["month"] = _month(per_day.date)
    hours = per_day.groupby(["generator_id", "month"], as_index=False).supply_hours.sum()

    # --- telemetry: imbalance per hour, then averaged ------------------------
    tel = pd.DataFrame(
        db.query(
            GeneratorTelemetry.generator_id,
            GeneratorTelemetry.timestamp,
            GeneratorTelemetry.current_l1,
            GeneratorTelemetry.current_l2,
            GeneratorTelemetry.current_l3,
            GeneratorTelemetry.fuel_rate_lph,
        ).all(),
        columns=["generator_id", "timestamp", "l1", "l2", "l3", "fuel_rate_lph"],
    )
    if tel.empty:
        imbalance = pd.DataFrame(
            columns=["generator_id", "month", "phase_imbalance_pct", "hours_above_flag_pct"]
        )
        fuel = pd.DataFrame(columns=["generator_id", "month", "fuel_litres"])
    else:
        tel["month"] = _month(tel.timestamp)

        currents = tel[["l1", "l2", "l3"]]
        mean = currents.mean(axis=1).replace(0, pd.NA)
        tel["imbalance_pct"] = 100.0 * (currents.max(axis=1) - currents.min(axis=1)) / mean
        tel["flagged"] = tel.imbalance_pct > IMBALANCE_FLAG_PCT

        imbalance = (
            tel.dropna(subset=["imbalance_pct"])
            .groupby(["generator_id", "month"], as_index=False)
            .agg(
                phase_imbalance_pct=("imbalance_pct", "mean"),
                hours_above_flag_pct=("flagged", lambda s: 100.0 * s.mean()),
            )
        )

        # Litres: the rate is litres per hour and each row is one sampled
        # hour, so the sum of the rates over a month is the litres burned in
        # the hours that were sampled. Null stays null.
        fuel = (
            tel.dropna(subset=["fuel_rate_lph"])
            .groupby(["generator_id", "month"], as_index=False)
            .fuel_rate_lph.sum()
            .rename(columns={"fuel_rate_lph": "fuel_litres"})
        )

    # --- alarms --------------------------------------------------------------
    al = pd.DataFrame(
        db.query(GeneratorAlarm.generator_id, GeneratorAlarm.timestamp).all(),
        columns=["generator_id", "timestamp"],
    )
    if al.empty:
        alarms = pd.DataFrame(columns=["generator_id", "month", "alarm_count"])
    else:
        al["month"] = _month(al.timestamp)
        alarms = al.groupby(["generator_id", "month"], as_index=False).size().rename(
            columns={"size": "alarm_count"}
        )

    frame = produced.merge(hours, on=["generator_id", "month"], how="left")
    for other in (imbalance, fuel, alarms):
        if not other.empty:
            frame = frame.merge(other, on=["generator_id", "month"], how="left")
    for col in ("phase_imbalance_pct", "hours_above_flag_pct", "fuel_litres", "alarm_count"):
        if col not in frame:
            frame[col] = None

    frame = frame.merge(gens[["generator_id", "ecu_connected"]], on="generator_id", how="left")
    frame["ecu_connected"] = frame.ecu_connected.fillna(False)

    # A fuel figure from a set with no ECU is not a small number, it is not a
    # number. Blank it rather than let a stray value through.
    frame.loc[~frame.ecu_connected.astype(bool), "fuel_litres"] = None
    frame["litres_per_kwh"] = (frame.fuel_litres / frame.produced_kwh.replace(0, pd.NA)).round(3)
    frame["alarm_count"] = frame.alarm_count.fillna(0).astype(int)
    return frame


def store(db: Session, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    db.query(GeneratorMonthMetrics).delete()
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [
        GeneratorMonthMetrics(
            generator_id=r.generator_id,
            month=r.month,
            produced_kwh=float(r.produced_kwh or 0.0),
            supply_hours=None if pd.isna(r.supply_hours) else float(r.supply_hours),
            fuel_litres=None if pd.isna(r.fuel_litres) else float(r.fuel_litres),
            litres_per_kwh=None if pd.isna(r.litres_per_kwh) else float(r.litres_per_kwh),
            ecu_connected=bool(r.ecu_connected),
            phase_imbalance_pct=None
            if pd.isna(r.phase_imbalance_pct)
            else round(float(r.phase_imbalance_pct), 1),
            hours_above_flag_pct=None
            if pd.isna(r.hours_above_flag_pct)
            else round(float(r.hours_above_flag_pct), 1),
            alarm_count=int(r.alarm_count or 0),
            computed_at=now,
        )
        for r in frame.itertuples()
    ]
    db.add_all(rows)
    db.commit()
    logger.info("generator_month_metrics rebuilt: %d rows", len(rows))
    return len(rows)


def refresh(db: Session) -> int:
    return store(db, compute(db))
