"""
The loss account: measure the gap, then explain it.

THE ONE SENTENCE THIS MODULE EXISTS FOR
---------------------------------------
"Explain the missing kWh. Theft is only what is left after everything else
has been explained."

Everything below is that sentence turned into arithmetic. It never returns a
figure called theft, and the word does not appear in any output, because the
system cannot prove theft and saying otherwise is how an owner is sent to
knock on innocent doors and then stops using the platform.

HOW THE SPLIT IS MADE
---------------------
Total loss is measured: energy delivered into a zone, minus the energy its
invoices billed for. That subtraction is the only part that is certain. The
five parts it is divided into are estimates, each from a different source, and
each is computed conservatively so that the residual is the LAST thing to grow
rather than the first.

  normal technical   Fitted, not assumed. Loss follows current squared, so the
                     best-performing zones on the same generator establish what
                     physics alone costs at this load, and every zone is
                     credited with that much.
  excess technical   The part of the gap that still tracks load after the
                     normal share is removed, plus the measured contribution of
                     phase imbalance on the feeding generator. Fixable, and the
                     briefing's "send a technician" line.
  measurement        Two measurable process defects: readings the OCR was not
                     confident about, and the mismatch between the generator's
                     calendar month and the ten-day window in which meters were
                     actually read.
  unbilled           The owner's own supply, from the connections table. Known,
                     named, and not a loss at all.
  unexplained        What is left. A shortlist for a field visit, with a
                     confidence attached, never a verdict.

WHY THE RESULT IS STORED RATHER THAN COMPUTED ON DEMAND
-------------------------------------------------------
The briefing forbids letting a language model do arithmetic, and requires that
every number in an answer come from a query result. So this runs once, writes
zone_loss_monthly, and everything else reads that table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.loss import ZoneLossMonthly
from app.models.network import Generator, GeneratorTelemetry, UnbilledConnection, Zone, ZoneEnergyDaily
from app.models.subscription import Meter, MeterReading, Subscription

logger = logging.getLogger(__name__)

# Imbalance above this is worth investigating (rag_documents/02, and the
# briefing's dashboard rule).
IMBALANCE_FLAG_PCT = 15.0

# A reading the OCR was less sure about than this is suspect, not wrong.
OCR_SUSPECT_BELOW = 0.80

# The share of a zone's energy that the best-performing comparable zones lose.
# Not a constant: measured per generator, per month, from the data itself.
BENCHMARK_QUANTILE = 0.20


@dataclass
class ZoneMonth:
    zone_id: str
    month: date
    delivered: float
    billed: float

    @property
    def loss(self) -> float:
        return self.delivered - self.billed

    @property
    def loss_pct(self) -> float | None:
        return 100.0 * self.loss / self.delivered if self.delivered > 0 else None


# ---------------------------------------------------------------------------
# The two measured quantities
# ---------------------------------------------------------------------------
def _delivered(db: Session) -> pd.DataFrame:
    """kWh into each zone each month, from the generator side."""
    rows = db.query(
        ZoneEnergyDaily.zone_id,
        ZoneEnergyDaily.date,
        ZoneEnergyDaily.energy_delivered_kwh,
        ZoneEnergyDaily.peak_current_a,
        ZoneEnergyDaily.supply_hours,
    ).all()
    df = pd.DataFrame(rows, columns=["zone_id", "date", "kwh", "peak_current_a", "supply_hours"])
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df.date).dt.to_period("M").dt.to_timestamp().dt.date
    return df.groupby(["zone_id", "month"], as_index=False).agg(
        delivered=("kwh", "sum"),
        peak_current=("peak_current_a", "max"),
        mean_current=("peak_current_a", "mean"),
        supply_hours=("supply_hours", "sum"),
    )


def _billed(db: Session) -> pd.DataFrame:
    """
    kWh each zone was invoiced for.

    units_consumed, not total_amount. The money on an invoice includes a fixed
    subscription charge paid whether or not a kilowatt-hour flows, so a total
    cannot be turned back into energy.
    """
    rows = db.query(Invoice.zone_id, Invoice.billing_period, Invoice.units_consumed).all()
    df = pd.DataFrame(rows, columns=["zone_id", "month", "units"])
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df.month).dt.to_period("M").dt.to_timestamp().dt.date
    return df.groupby(["zone_id", "month"], as_index=False).units.sum().rename(
        columns={"units": "billed"}
    )


# ---------------------------------------------------------------------------
# The five parts
# ---------------------------------------------------------------------------
def _normal_technical(frame: pd.DataFrame) -> pd.Series:
    """
    What physics costs, measured rather than assumed.

    The temptation is to write down a percentage from a textbook. The zones
    are a better instrument than any textbook: they share a generator, a
    month, a tariff and the weather, so the quietest of them shows what this
    network loses when nothing is wrong. That floor is what every zone is
    credited with as unavoidable.

    Two corrections, both in the direction of crediting MORE to physics and
    therefore leaving LESS unexplained, which is the safe direction to be
    wrong in when the residual is what sends somebody to a customer's door:

      distance  loss rises with cable length, so a zone 500 m out is expected
                to lose more than one at 150 m before anything is wrong.
      load      loss follows current squared, so a heavily loaded month is
                expected to lose a larger share than a quiet one.
    """
    # `frame` already carries generator_id and avg_distance_m from the zone
    # join in compute(). Merging them again here would produce generator_id_x
    # and generator_id_y and quietly break every groupby below.
    df = frame.copy()

    # The physical predictor: loss = I squared x R, and R grows with the length
    # of the cable. So what a zone-month should cost in pure heat is
    # proportional to distance times current squared.
    df["predictor"] = df.avg_distance_m.fillna(df.avg_distance_m.median()) * (
        df.mean_current.fillna(df.mean_current.median()) ** 2
    )
    df["observed_share"] = (df.delivered - df.billed) / df.delivered.replace(0, pd.NA)

    # k is the cost per unit of predictor: how much loss this network suffers
    # for each metre-ampere-squared. Fitted from the QUIETEST fifth of
    # zone-months on the same generator, which is what makes it a floor rather
    # than an average. An average would absorb the very excess we are looking
    # for into the thing we call unavoidable.
    #
    # Dividing the observed share by that zone's own predictor first is the
    # step that stops distance and load being counted twice: the benchmark
    # zone already has its own length and its own load baked into its loss,
    # and multiplying its share by another zone's distance ratio on top of
    # that inflates physics until it swallows the entire gap. That is exactly
    # what happened before this was rewritten, and it left an unexplained
    # residual of 0.1% - a system that finds nothing is as useless as one that
    # accuses everybody.
    df["unit_cost"] = df.observed_share / df.predictor.replace(0, pd.NA)
    k = df.groupby(["generator_id", "month"]).unit_cost.transform(
        lambda s: s.quantile(BENCHMARK_QUANTILE)
    )
    k = k.fillna(df.unit_cost.quantile(BENCHMARK_QUANTILE))

    expected_share = (k * df.predictor).clip(lower=0.0)
    return (expected_share * df.delivered).fillna(0.0)


def _phase_imbalance_by_generator(db: Session) -> pd.DataFrame:
    """
    Average imbalance per generator per month, and the share of hours above
    the flag.

    Unequal phase currents return through the neutral, which has resistance,
    and that heat serves no customer. It is one of the few loss causes visible
    from a desk and fixable in an afternoon, which is exactly what the owner
    wants to hear.
    """
    rows = db.query(
        GeneratorTelemetry.generator_id,
        GeneratorTelemetry.timestamp,
        GeneratorTelemetry.current_l1,
        GeneratorTelemetry.current_l2,
        GeneratorTelemetry.current_l3,
    ).all()
    df = pd.DataFrame(rows, columns=["generator_id", "timestamp", "l1", "l2", "l3"]).dropna(
        subset=["l1", "l2", "l3"]
    )
    if df.empty:
        return pd.DataFrame(columns=["generator_id", "month", "imbalance_pct", "hours_flagged_pct"])

    df["month"] = pd.to_datetime(df.timestamp).dt.to_period("M").dt.to_timestamp().dt.date
    currents = df[["l1", "l2", "l3"]]
    mean = currents.mean(axis=1).replace(0, pd.NA)
    df["imbalance_pct"] = 100.0 * (currents.max(axis=1) - currents.min(axis=1)) / mean
    df["flagged"] = df.imbalance_pct > IMBALANCE_FLAG_PCT

    return df.groupby(["generator_id", "month"], as_index=False).agg(
        imbalance_pct=("imbalance_pct", "mean"),
        hours_flagged_pct=("flagged", lambda s: 100.0 * s.mean()),
    )


def _measurement_loss(db: Session) -> pd.DataFrame:
    """
    The part of the gap caused by how the reading was taken, not by where the
    electricity went.

    Two contributions, both measured from the data rather than assumed:

    OCR uncertainty. A reading the recogniser was unsure about carries an
    expected error proportional to how unsure it was. Summed across a zone's
    suspect readings, that is a real quantity of energy that may be on the
    wrong side of the ledger.

    Window mismatch. The generator's month runs 1 to 31; the meters are read
    over about ten days somewhere inside it. The two totals therefore cover
    different periods, and the difference is worth a share of a month's energy
    with nothing whatever wrong. It is estimated as the fraction of the month
    by which the reading window is displaced.
    """
    rows = (
        db.query(
            Subscription.zone_id,
            MeterReading.billing_period,
            MeterReading.reading_value,
            MeterReading.ocr_confidence,
            MeterReading.reading_date,
            MeterReading.subscription_id,
            Meter.initial_reading,
        )
        .join(Subscription, Subscription.subscription_id == MeterReading.subscription_id)
        .outerjoin(Meter, Meter.meter_id == MeterReading.meter_id)
        .all()
    )
    df = pd.DataFrame(
        rows,
        columns=[
            "zone_id", "month", "reading", "ocr", "reading_date",
            "subscription_id", "initial_reading",
        ],
    )
    if df.empty:
        return pd.DataFrame(columns=["zone_id", "month", "measurement_kwh"])

    df["month"] = pd.to_datetime(df.month).dt.to_period("M").dt.to_timestamp().dt.date
    df = df.sort_values(["subscription_id", "month"])
    # Seeded from the dial at installation, so the earliest month of each meter
    # is differenced like every other one instead of being dropped. Without it
    # a suspect first reading contributes no OCR error at all, which understates
    # this part of the account for exactly the readings nobody has checked.
    df["prev"] = df.groupby("subscription_id").reading.shift(1).fillna(df.initial_reading)
    df["consumed"] = df.reading - df.prev

    # --- OCR: expected error scales with how unsure the recogniser was ------
    suspect = df[df.ocr.notna() & (df.ocr < OCR_SUSPECT_BELOW)].copy()
    suspect["error_kwh"] = suspect.consumed.abs().fillna(0.0) * (1.0 - suspect.ocr)
    ocr_part = suspect.groupby(["zone_id", "month"], as_index=False).error_kwh.sum().rename(
        columns={"error_kwh": "ocr_kwh"}
    )

    # --- Window: how far the reading window sits from the month boundary ----
    df["reading_date"] = pd.to_datetime(df.reading_date)
    window = df.dropna(subset=["reading_date"]).copy()
    window["offset_days"] = (
        window.reading_date - pd.to_datetime(window.month)
    ).dt.days.clip(lower=0)
    per = window.groupby(["zone_id", "month"], as_index=False).agg(
        mean_offset=("offset_days", "mean"), consumed=("consumed", "sum")
    )
    # A reading window displaced by d days out of ~30 misattributes roughly
    # d/30 of a month's consumption between two periods. Successive months
    # largely cancel, so only the month-to-month VARIATION in that offset is
    # a real error; a constant offset is a constant, not a loss.
    per["drift"] = per.groupby("zone_id").mean_offset.transform(lambda s: (s - s.mean()).abs())
    per["window_kwh"] = (per.drift / 30.0) * per.consumed.abs().fillna(0.0)
    window_part = per[["zone_id", "month", "window_kwh"]]

    out = ocr_part.merge(window_part, on=["zone_id", "month"], how="outer").fillna(0.0)
    out["measurement_kwh"] = out.ocr_kwh + out.window_kwh
    return out[["zone_id", "month", "measurement_kwh"]]


def _unbilled(db: Session) -> pd.DataFrame:
    """The owner's own supply. Known, named, and not a loss."""
    rows = db.query(UnbilledConnection.zone_id, UnbilledConnection.est_kwh_per_month).all()
    df = pd.DataFrame(rows, columns=["zone_id", "kwh"])
    if df.empty:
        return pd.DataFrame(columns=["zone_id", "unbilled_kwh"])
    return df.groupby("zone_id", as_index=False).kwh.sum().rename(columns={"kwh": "unbilled_kwh"})


# ---------------------------------------------------------------------------
def compute(db: Session) -> pd.DataFrame:
    """Build the whole account. Returns the frame it also stores."""
    delivered = _delivered(db)
    billed = _billed(db)
    if delivered.empty or billed.empty:
        logger.warning("No delivered or billed energy: nothing to account for")
        return pd.DataFrame()

    frame = delivered.merge(billed, on=["zone_id", "month"], how="left")
    frame["billed"] = frame.billed.fillna(0.0)
    frame["loss_kwh"] = frame.delivered - frame.billed
    frame["loss_pct"] = 100.0 * frame.loss_kwh / frame.delivered.replace(0, pd.NA)

    zone_rows = db.query(Zone.zone_id, Zone.name, Zone.generator_id, Zone.avg_distance_m).all()
    zones = pd.DataFrame(zone_rows, columns=["zone_id", "zone_name", "generator_id", "avg_distance_m"])
    frame = frame.merge(zones, on="zone_id", how="left")

    # --- 1. physics ---------------------------------------------------------
    frame["normal_technical_kwh"] = _normal_technical(frame)

    # --- 3. measurement -----------------------------------------------------
    meas = _measurement_loss(db)
    frame = frame.merge(meas, on=["zone_id", "month"], how="left")
    frame["measurement_kwh"] = frame.measurement_kwh.fillna(0.0)

    # --- 4. the owner's own supply -----------------------------------------
    unb = _unbilled(db)
    frame = frame.merge(unb, on="zone_id", how="left")
    frame["unbilled_kwh"] = frame.unbilled_kwh.fillna(0.0)

    # --- 2. excess technical ------------------------------------------------
    # What remains after physics, measurement and the owner's own supply, but
    # only the part that still moves with load: that is the signature of a
    # cable problem rather than of a fixed draw. Phase imbalance on the
    # feeding generator is the evidence that decides how much of it to claim.
    imb = _phase_imbalance_by_generator(db)
    frame = frame.merge(imb, on=["generator_id", "month"], how="left")
    frame["imbalance_pct"] = frame.imbalance_pct.fillna(0.0)

    # --- allocation ---------------------------------------------------------
    # THE PARTS MUST SUM TO THE MEASURED LOSS. Exactly, every row.
    #
    # Each part above is an independent estimate from a different source, so
    # nothing stops them totalling more than the gap they are dividing, and
    # the first version of this file did exactly that: the five parts came to
    # 215,104 kWh against a measured loss of 163,739. An account whose parts
    # do not add up to the whole is not an account, and it is precisely the
    # kind of number that survives a demo and dies at a defence.
    #
    # So the gap is allocated with a running remainder, in order of how
    # certain each claim is:
    #
    #   1. unbilled       a list the owner wrote. Known energy, not loss.
    #   2. measurement    measured from OCR confidence and the reading window.
    #   3. normal         the fitted physics floor.
    #   4. excess         evidenced by phase imbalance on the feeder.
    #   5. unexplained    whatever is left, and nothing more.
    #
    # A part that would overrun the remainder is truncated to it, and the row
    # records that it was, because a truncated estimate is information: it
    # says the explanations available already exceed the gap being explained.
    gap = frame.loss_kwh.clip(lower=0.0)
    remaining = gap.copy()
    frame["estimates_exceeded_gap"] = False

    def take(wanted: pd.Series) -> pd.Series:
        nonlocal remaining
        wanted = wanted.fillna(0.0).clip(lower=0.0)
        taken = pd.concat([wanted, remaining], axis=1).min(axis=1)
        frame["estimates_exceeded_gap"] |= wanted > remaining + 1e-9
        remaining = (remaining - taken).clip(lower=0.0)
        return taken

    frame["unbilled_kwh"] = take(frame.unbilled_kwh)
    frame["measurement_kwh"] = take(frame.measurement_kwh)
    frame["normal_technical_kwh"] = take(frame.normal_technical_kwh)

    # Imbalance beyond the flag is heat serving nobody. Its share of what is
    # still unallocated is capped at half: imbalance is evidence of a fixable
    # fault, not a measurement of what that fault costs, and claiming more
    # would quietly shrink the residual on the strength of a proxy.
    imbalance_share = ((frame.imbalance_pct - IMBALANCE_FLAG_PCT) / 100.0).clip(0.0, 0.5)
    frame["excess_technical_kwh"] = take(remaining * imbalance_share)

    # --- 5. what is left ----------------------------------------------------
    frame["unexplained_kwh"] = remaining

    # --- how much to trust the split ----------------------------------------
    # Thin where the evidence is thin: a generator with no ECU, a month with
    # few readings, a zone with almost no load to fit a curve against.
    ecu = pd.DataFrame(
        db.query(Generator.generator_id, Generator.ecu_connected).all(),
        columns=["generator_id", "ecu_connected"],
    )
    frame = frame.merge(ecu, on="generator_id", how="left")
    frame["confidence"] = (
        0.5
        + 0.2 * frame.ecu_connected.fillna(False).astype(float)
        + 0.2 * (frame.imbalance_pct > 0).astype(float)
        + 0.1 * (frame.measurement_kwh > 0).astype(float)
    ).clip(0.0, 1.0)

    frame["method_note"] = frame.apply(
        lambda r: (
            f"physics floor fitted at the {BENCHMARK_QUANTILE:.0%} quantile of zones on "
            f"{r.generator_id}; imbalance {r.imbalance_pct:.0f}%; "
            f"{'ECU present' if r.ecu_connected else 'no ECU, fuel checks unavailable'}"
            + ("; estimates exceeded the measured gap and were truncated"
               if r.estimates_exceeded_gap else "")
        ),
        axis=1,
    )
    return frame


def check_adds_up(frame: pd.DataFrame, tolerance: float = 0.5) -> list[str]:
    """
    Every row's five parts must sum to its measured loss.

    Returned rather than asserted so a caller can report it; the loader and
    the test suite both call this, because a split that does not reconcile is
    worse than no split at all.
    """
    if frame.empty:
        return []
    parts = frame[
        [
            "normal_technical_kwh",
            "excess_technical_kwh",
            "measurement_kwh",
            "unbilled_kwh",
            "unexplained_kwh",
        ]
    ].sum(axis=1)
    drift = (parts - frame.loss_kwh.clip(lower=0.0)).abs()
    bad = frame[drift > tolerance]
    return [
        f"{r.zone_id} {r.month}: parts sum to {p:,.1f} kWh but loss is {r.loss_kwh:,.1f} kWh"
        for r, p in zip(bad.itertuples(), parts[drift > tolerance])
    ]


def store(db: Session, frame: pd.DataFrame) -> int:
    """Replace zone_loss_monthly with this account."""
    if frame.empty:
        return 0
    db.query(ZoneLossMonthly).delete()
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [
        ZoneLossMonthly(
            zone_id=r.zone_id,
            month=r.month,
            energy_delivered_kwh=float(r.delivered),
            units_billed_kwh=float(r.billed),
            loss_kwh=float(r.loss_kwh),
            loss_pct=None if pd.isna(r.loss_pct) else float(r.loss_pct),
            normal_technical_kwh=float(r.normal_technical_kwh),
            excess_technical_kwh=float(r.excess_technical_kwh),
            measurement_kwh=float(r.measurement_kwh),
            unbilled_kwh=float(r.unbilled_kwh),
            unexplained_kwh=float(r.unexplained_kwh),
            confidence=float(r.confidence),
            method_note=str(r.method_note)[:255],
            computed_at=now,
        )
        for r in frame.itertuples()
    ]
    db.add_all(rows)
    db.commit()
    logger.info("zone_loss_monthly rebuilt: %d rows", len(rows))
    return len(rows)


def refresh(db: Session) -> int:
    return store(db, compute(db))
